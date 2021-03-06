import os
import io
import json
import copy
import boto3
import base64
import datetime
import numpy as np
from PIL import Image
from io import BytesIO
from requests_toolbelt.multipart import decoder

from tensorflow.keras.models import load_model
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input

s3 = boto3.client('s3')
model = load_model("/var/task/mobilenetv2")
not_enc_bucket = 'request-image-not-encrypted'

def save_img_s3(img, bucket_name):
    in_mem_file = io.BytesIO()
    img.save(in_mem_file, format=img.format)
    in_mem_file.seek(0)
    now = datetime.datetime.now()
    filename = f"{now.strftime('%H%M%S')}.{img.format}"
    s3.upload_fileobj(in_mem_file, bucket_name,
                      f'{now.year}/{now.month}/{now.day}/{filename}',
                      ExtraArgs={'ACL': 'public-read'})
    return 0

def multipart_to_input(multipart_data):
    binary_content = []
    for part in multipart_data.parts:
        binary_content.append(part.content)

    img = BytesIO(binary_content[0])
    img = Image.open(img)
    
    save_img_s3(img, not_enc_bucket)

    img = img.resize((224, 224), Image.ANTIALIAS)
    img = np.array(img)
    
    # 1, 224, 224, 3
    img = img.reshape((1, img.shape[0], img.shape[1], img.shape[2]))
    img = preprocess_input(img)
    return img

def decode_predictions(preds, top=5):
    with open('/var/task/imagenet_class_index.json') as f:
        CLASS_INDEX = json.load(f)
    results = []
    for pred in preds:
        top_indices = pred.argsort()[-top:][::-1]
        result = [tuple(CLASS_INDEX[str(i)]) + (pred[i],) for i in top_indices]
        result.sort(key=lambda x: x[2], reverse=True)
        results.append(result)
    return results

def inference_model(img):
    result = model.predict(img)
    result = decode_predictions(result)[0]
    result = [(img_class, label, str(round(acc * 100, 4)) + '%') for img_class, label, acc in result]
    return result
    
def handler(event, context):
    
    body = event['body-json']
    body = base64.b64decode(body)
    
    boundary = body.split(b'\r\n')[0]
    boundary = boundary.decode('utf-8')
    content_type = f"multipart/form-data; boundary={boundary}"
    
    multipart_data = decoder.MultipartDecoder(body, content_type)
    
    try:
        img = multipart_to_input(multipart_data)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps(f"{e}")
        }

    result = inference_model(img)
    
    return {
        'statusCode': 200,
        'body': json.dumps(f"{result[0][1]}&{result[0][2]}&{result[1][1]}&{result[1][2]}&{result[2][1]}&{result[2][2]}&{result[3][1]}&{result[3][2]}&{result[4][1]}&{result[4][2]}")
    }
