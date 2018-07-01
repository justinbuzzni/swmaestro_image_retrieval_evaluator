# coding:utf-8
import sys

import numpy as np
import pandas as pd
import pendulum
import pyltr
from flasgger import Swagger
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient, DESCENDING
from sklearn.externals import joblib

import config

app = Flask(__name__)
swagger = Swagger(app)

client = MongoClient('mongodb://%s:%s@%s' % (config.mongo_username,
                                             config.mongo_password,
                                             config.mongo_host))

SCORE_DB = client['soma_2018']
score_history_db = SCORE_DB['score_history']

eval_qid_gold_list_dict = joblib.load(config.eval_gold_file_path)
test160_qid_gold_list_dict = joblib.load(config.test160_gold_file_path)
test500_qid_gold_list_dict = joblib.load(config.test500_gold_file_path)
qid_gold_list_dict = {'eval': eval_qid_gold_list_dict,
                      'test160': test160_qid_gold_list_dict,
                      'test500': test500_qid_gold_list_dict}


def add_score_data(name, nickname, score, email, mode, ip, day):
    '''
    점수 기록을 score_history 와 score 에 추가한다
    단 score 에 추가할때에는 점수가 더 좋을때만 추가한다.
    @param name: 실명
    @param nickname: 점수판 표시용 이름
    @param score: 검색 성능 점수
    @param email: email
    @return:
    '''
    score_history_db.insert_many([{'nickname': nickname, 'name': name, 'score': score, 'date': pendulum.now(),
                                   'email': email, 'mode': mode, 'ip': ip, 'day': day}])
    prev_score_info = SCORE_DB[mode + "_score"].find_one({'nickname': nickname})
    if prev_score_info:
        if prev_score_info['score'] > score:
            '''
            새로 업데이트 하는 것의 점수가 이전 최고 기록보다 점수가 낮은 경우이다. 이때는 점수를 업데이트 하지 않는다.
            '''
            return False
    SCORE_DB[mode + "_score"].update_one({'nickname': nickname},
                                         {'$set': {'name': name, 'nickname': nickname, 'score': score,
                                                   'date': pendulum.now(), 'email': email}}, upsert=True)
    return True


@app.route("/", methods=['POST'])
def evaluation():
    '''
    pred_result 에 대한 ndcg 성능 평가 결과를 반환한다.
    평가 서버에 요청할때에는 아래와 같이 요청 가능하다.
    mode 는  eval, test160, test500 3가지가 가능하다. eval 는 파라미터 최적화 할때 사용하고 여기서 최적화된 파라미터로 test160/test500 에 최종 성능을 평가한다.
    test160 는 한 ip 당 일 1회 요청 제한이 있다.
    r = requests.post('http://eval.buzzni.net:31000', json={"pred_result": system_result_dict})
    print r.json()

    name = 'gil-dong Hong'
    nickname = 'gil-dong'
    email = 'email'
    mode = 'test160'
    r = requests.post('http://eval.buzzni.net:31000', json={"pred_result": system_result_dict,'name':name, 'nickname':nickname, 'mode':mode,'email':email})
    print (r.json())

    system_result_dict 에는 query_id 별로 해당 query image 와 가장 비슷한 20개의 이미지 id 리스트를 가지고 있다.
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

      - name: email
        in: query
        type: string
        required: true

      - name: mode
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
    email = request.get_json().get('email', '')
    mode = request.get_json().get('mode', 'eval')
    ip = request.remote_addr
    now_day = pendulum.now().format('%Y%m%d')
    if not name:
        return jsonify({'msg': 'name parameter required! - http://eval.buzzni.net:31000/apidocs/#/default/post_'})
    if not nickname:
        return jsonify({'msg': 'nickname parameter required! - http://eval.buzzni.net:31000/apidocs/#/default/post_'})
    if mode not in ['eval', 'test160', 'test500']:
        return jsonify({'msg': 'mode value (eval or test) parameter required! - http://eval.buzzni.net:31000/apidocs/#/default/post_'})
    if not email:
        return jsonify({'msg': 'email parameter required! - http://eval.buzzni.net:31000/apidocs/#/default/post_'})
    mode_size_dict = {'eval': 160, 'test160': 160, 'test500': 495}

    if len(system_result_dict.keys()) != mode_size_dict[mode]:
        return jsonify({'msg': 'expected result num is 160, but current result num is %d' % len(system_result_dict.keys())})
    if mode in ['test160']:
        prev_history = score_history_db.find_one({'mode': mode, 'ip': ip, 'day': now_day})
        if prev_history:
            return jsonify({'msg': 'you can submit only one result in a day'})

    search_gold_y_list = []
    search_system_y_list = []
    search_qid_list = []
    for qid in qid_gold_list_dict[mode].keys():
        system_key_score_dict = {}

        for idx, k in enumerate(system_result_dict[qid]):
            '''
            아래와 같이 3등 이내일때 더 높은 점수를 주는 이유는 상위 검색 결과에서 매칭 되는 경우에 더 높은 점수를 부여하고자 하기 때문이다
            '''
            if idx < 3:
                system_key_score_dict[k] = 2
            elif idx < len(qid_gold_list_dict[mode][qid]) / 2.0:
                '''
                query 에 따라서 gold 에 포함되는 이미지 개수가 다 가변적이라서, 위와 같이 하였다.
                '''
                system_key_score_dict[k] = 1.5

            elif idx < len(qid_gold_list_dict[mode][qid]):
                system_key_score_dict[k] = 1

        key_gold_score_dict = {}
        for key in qid_gold_list_dict[mode][qid]:
            key_gold_score_dict[key] = 1
        max_limit = np.min([len(qid_gold_list_dict[mode][qid]), 10])
        # for key in list(system_key_score_dict.keys())[:len(qid_gold_list_dict[mode][qid])]:
        for key in list(system_key_score_dict.keys())[:max_limit]:
            search_qid_list.append(qid)
            search_gold_y_list.append(key_gold_score_dict.get(key, 0))
            search_system_y_list.append(system_key_score_dict.get(key))
    # 평가 할때마다 만들어줘야함
    metric = pyltr.metrics.NDCG(k=10)
    score = metric.calc_mean(search_qid_list, np.asarray(search_gold_y_list), np.asarray(search_system_y_list))
    if score > 1:
        return jsonify({'msg': 'invalid score ' + str(score)})
    print('score:', score)
    result = {'score': score}
    add_score_data(name=name, nickname=nickname, score=score, email=email, mode=mode, ip=ip, day=now_day)
    return jsonify(result)


@app.route("/leader_board")
def show_leader_board():
    filter_mode = request.args.get("mode", '')
    score_data_list = []
    titles = ['na']
    for mode in ['test160', 'eval', 'test500']:
        if filter_mode:
            if mode != filter_mode:
                continue

        score_list = []
        rank = 1
        for each in SCORE_DB[mode + "_score"].find().sort([("score", DESCENDING)]).limit(300):
            score_list.append({'rank': rank, 'name': each['nickname'], 'score': each['score']})
            rank += 1
        if not score_list:
            continue

        data = pd.DataFrame(score_list)
        data.set_index(['name'], inplace=True)
        data.index.name = None
        score_data_list.append(data.to_html())
        titles.append(mode + " Leaderbaord")

    return render_template('leader_board.html', tables=score_data_list, titles=titles)


if __name__ == '__main__':
    # test()
    port = int(sys.argv[1])
    print("port")
    app.debug = True
    app.run(host='0.0.0.0', port=int(sys.argv[1]))
