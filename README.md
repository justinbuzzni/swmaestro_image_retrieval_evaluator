# swmaestro_image_retrieval_evaluator
software maestro 2018 backend - image retrieval contest evaluation server
 * score leader board : http://eval.buzzni.net:31000/leader_board
 * data set : https://www.dropbox.com/s/pbui2jycsuimomu/fashion_retrieval_img.tar.gz?dl=0
    * query folder : query image
    * compare folder : search target image 
 * how to make evaluation? 
    1. iterate all query image and calculate distance with all compare image.
    2. sort compare image by distance (asc)
    3. upload the result (160 query)    
 * evaluation server : http://eval.buzzni.net:31000
 * api description : http://eval.buzzni.net:31000/apidocs/#/  
 * sample upload evaluation code
  ```python
system_result_dict = {}
for each in glob("/home/maestro_2018/test/img/query/*"):
    fname = each.split("/")[-1]
    score_dict = {}
    for other in glob("/home/maestro_2018/test/img/compare/*"):
        fname2 = other.split("/")[-1]
        dist = cosine(img_feature_dict[fname], img_feature_dict[fname2])
        score_dict[fname2] = dist
    sorted_list = sorted(score_dict.items(), key=lambda (k,v):(v,k), reverse=False)
    qid = fname.split("_")[-1].split(".")[0]
    system_result_dict[qid] = map(lambda i : i[0], sorted_list[:20])
          
name = 'buzzni-200'
nickname = 'buzzni-200'
r = requests.post('http://eval.buzzni.net:31000', json={"pred_result": system_result_dict,'name':name, 'nickname':nickname})
print r.json()
```  
 * 버즈니에서 개발자 채용을 하고 있습니다 관심 있는 분들은 recruit@buzzni.com 로 연락 주세요. 전문연구요원, 보충역 가능합니다.