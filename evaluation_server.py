# coding:utf-8
import sys
import numpy as np
from time import sleep
from random import sample
from glob import glob

from sklearn.externals import joblib
from flask import Flask, request, jsonify, render_template, request
from flask_restful import Api
from flask_restful import Resource
from flasgger import Swagger
import pyltr
from pymongo import MongoClient, DESCENDING
import pandas as pd
import pendulum

import config

app = Flask(__name__)
swagger = Swagger(app)

metric = pyltr.metrics.NDCG(k=10)
client = MongoClient('mongodb://%s:%s@%s' % (config.mongo_username,
                                             config.mongo_password,
                                             config.mongo_host))

score_history_db = client['soma_2018']['score_history']
score_db = client['soma_2018']['score']

qid_gold_list_dict = {}
with open(config.gold_file_path) as fin:
    data = fin.read().strip()
    for line in data.split("\n"):
        qid, data = line.strip().split(" | ")
        qid_gold_list_dict[qid] = data.split(",")

candidate_list = []
for each in glob(config.candidate_file_path+"/*"):
    candidate_list.append(each.split("/")[-1])


def add_score_data(name, nickname, score):
    '''
    점수 기록을 score_history 와 score 에 추가한다
    단 score 에 추가할때에는 점수가 더 좋을때만 추가한다.
    @param name: 실명
    @param nickname: 점수판 표시용 이름
    @param score: 검색 성능 점수
    @return:
    '''
    score_history_db.insert_many([{'nickname': nickname, 'name': name, 'score': score, 'date': pendulum.now()}])
    prev_score_info = score_db.find_one({'_id': name})
    if prev_score_info:
        if prev_score_info['score'] > score:
            '''
            새로 업데이트 하는 것의 점수가 이전 최고 기록보다 점수가 낮은 경우이다. 이때는 점수를 업데이트 하지 않는다.
            '''
            return False
    score_db.update_one({'_id': name}, {'$set': {'nickname': nickname, 'score': score, 'date': pendulum.now()}}, upsert=True)
    return True


@app.route("/", methods=['POST'])
def evaluation():
    '''
    pred_result 에 대한 ndcg 성능 평가 결과를 반환한다.
    평가 서버에 요청할때에는 아래와 같이 요청 가능하다.
    r = requests.post('http://115.68.223.177:31001', json={"pred_result": system_result_dict})
    print r.json()

    system_result_dict 에는 query_id 별로 해당 query image 와 가장 비슷한 10개의 이미지 id 리스트를 가지고 있다.
    이미지 id 의 순서는 더 비슷한 순서대로 들어 있어야 한다.
    {'1': ['57aaa9e3efd3e84d8d906cd95c6da6a9.jpg',
      'd6c86e7ae73003d8c848baa0a95720f9.jpg' .. ]
     '10': ['2b2ec56ebd933b0dbb3818d17244519b.jpg',
      '9f27802f1a4dba04774ab9bc252bd122.jpg'..] .. }
    ---
    parameters:
      - name: pred_result
        in: prediction
        type: query
        required: true

      - name: name
        in: query
        type: string
        required: true

      - name: nickname
        in: query
        type: string
        required: true
    responses:
      200:
        description: prediction score
        examples:
          {score: 0.2}
    '''
    system_result_dict = request.get_json()['pred_result']
    name = request.get_json().get('name', '')
    nickname = request.get_json().get('nickname', '')

    if not name:
        return jsonify({'msg': 'name parameter required! - http://115.68.223.177:31001/apidocs/#/default/post_'})
    if not nickname:
        return jsonify({'msg': 'nickname parameter required! - http://115.68.223.177:31001/apidocs/#/default/post_'})

    if len(system_result_dict.keys()) != 160:
        return jsonify({'msg': 'expected result num is 160, but current result num is %d' % len(system_result_dict.keys())})

    search_gold_y_list = []
    search_system_y_list = []
    search_qid_list = []
    for qid in qid_gold_list_dict.keys():
        system_key_score_dict = {}

        for idx, k in enumerate(system_result_dict[qid]):
            '''
            아래와 같이 3등 이내일때 더 높은 점수를 주는 이유는 상위 검색 결과에서 매칭 되는 경우에 더 높은 점수를 부여하고자 하기 때문이다
            '''
            if idx < 3:
                system_key_score_dict[k] = 2
            elif idx < len(qid_gold_list_dict[qid]) / 2.0:
                '''
                query 에 따라서 gold 에 포함되는 이미지 개수가 다 가변적이라서, 위와 같이 하였다.
                '''
                system_key_score_dict[k] = 1.5

            elif idx < len(qid_gold_list_dict[qid]):
                system_key_score_dict[k] = 1

        key_gold_score_dict = {}
        for key in qid_gold_list_dict[qid]:
            key_gold_score_dict[key] = 1

        for key in list(system_key_score_dict.keys())[:len(qid_gold_list_dict[qid])]:
            search_qid_list.append(qid)
            search_gold_y_list.append(key_gold_score_dict.get(key, 0))
            search_system_y_list.append(system_key_score_dict.get(key))

    score = metric.calc_mean(search_qid_list, np.asarray(search_gold_y_list), np.asarray(search_system_y_list))
    if score > 1:
        return jsonify({'msg': 'invalid score ' + str(score)})
    print('score:', score)
    result = {'score': score}
    add_score_data(name=name, nickname=nickname, score=score)
    return jsonify(result)


@app.route("/leader_board")
def show_leader_board():

    score_list = []
    rank = 1
    for each in score_db.find().sort([("score", DESCENDING)]):
        score_list.append({'rank': rank, 'name': each['nickname'], 'score': each['score']})
        rank += 1
    data = pd.DataFrame(score_list)
    data.set_index(['name'], inplace=True)
    data.index.name = None
    return render_template('leader_board.html', tables=[data.to_html()], titles=['na', 'Leader Board'])

if __name__ == '__main__':
    # test()
    port = int(sys.argv[1])
    app.run(host='0.0.0.0', port=int(sys.argv[1]))
