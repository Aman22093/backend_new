
import requests
import httpx
import html5lib
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
import time
import re
from selenium.webdriver.common.by import By
import json
import os
import openai
from flask_cors import CORS
import textwrap
import torch
import time
import os
import re
import requests
from flask import Flask
from flask import jsonify
from flask import request
user_search_history = []

import torch
torch.cuda.empty_cache()
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
os.environ['OPENAI_API_KEY'] = ""
openai.api_key = os.getenv('OPENAI_API_KEY')

def flipkart(product_url, num_pages=5):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)

    product_data = {
        "URL":product_url,
        "name": None,
        "img_url": None,
        "Reviews": [],
        "Product_details": []
    }

    try:
        driver.get("https://www.flipkart.com/")
        time.sleep(2)

        driver.get(product_url)
        driver.implicitly_wait(10)

        # Locate the product name
        try:
            product_name = driver.find_element(By.CSS_SELECTOR, "h1._6EBuvT .VU-ZEz").text
            print("Product Name:", product_name)
            product_data["name"] = product_name
        except Exception as e:
            print(f"Error finding product name: {e}")
            
        # Locate the product image link
        try:
            image_element = driver.find_element(By.CSS_SELECTOR, "div._4WELSP._6lpKCl img")
            img_link = image_element.get_attribute("src")
            print("Image Link:", img_link)
            product_data["img_url"] = img_link
        except Exception as e:
            print(f"Error finding image link: {e}")

        # Locate the product details
        try:
            tables = driver.find_elements(By.CLASS_NAME, '_0ZhAN9')

            all_product_details = []

            for table in tables:
                product_details = {}

                try:
                    rows = table.find_elements(By.TAG_NAME, 'tr')
                    for row in rows:
                        row_text = row.text.split('\n')
                        if len(row_text) == 2:
                            key, value = row_text
                            product_details[key] = value
                except Exception as e:
                    print(f"Error finding rows: {e}")
                    continue

                if product_details:
                    all_product_details.append(product_details)

            product_data["Product_details"] = all_product_details

            # Print all product details
            print("\"All_Product_Details\":[")
            for i, product_detail in enumerate(all_product_details):
                print("    {")
                for key, value in product_detail.items():
                    print(f"        \"{key}\": \"{value}\",")
                if i < len(all_product_details) - 1:
                    print("    },")
                else:
                    print("    }")
            print("]")

        except Exception as e:
            print(f"Error: {e}")

        # Create review page URLs
        match = re.search(r'(.*?)/p/', product_url)
        if match:
            prefix = match.group(1)
            reviews_url = product_url.replace('/p/', '/product-reviews/')
            match = re.search(r'(.*?)marketplace=FLIPKART', reviews_url)
            if match:
                reviews_url = match.group(1) + 'marketplace=FLIPKART'
            review_page_urls = [reviews_url + f'&page={x}' for x in range(1, num_pages + 1)]

            # Iterate through each review page URL
            for page_url in review_page_urls:
                driver.get(page_url)
                elements = driver.find_elements(By.CLASS_NAME, "ZmyHeo")

                json_data = []

                for element in elements:
                    content = element.text
                    json_object = {"content": content}
                    json_data.append(json_object)

                product_data["Reviews"].extend(json_data)
           
                print(json_data)

    finally:
        driver.quit()
    with open('reviews.json', 'w') as json_file:
        json.dump(product_data, json_file, indent=4)

    return product_data

def get_response(prompt,model="gpt-4o"):
    messages=[{"role":"user","content":prompt}]
    response=openai.ChatCompletion.create(
        model=model,
        messages=messages
    )
    return response.choices[0].message["content"]

@app.route('/api/get_search_history',methods=['GET'])
def get_search_history():
    # Remove duplicates based on product_url
    unique_search_history = {entry['product_url']: entry for entry in user_search_history}.values()

    response = jsonify({
        'search_history': list(unique_search_history)
    })
    response.status_code = 200
    return response


@app.route('/api')
def home():
    data = {'message': "Server Working !!"}
    return data


@app.route('/api/set_search_history',methods=['POST'])
def set_search_history():
    search_term = request.json.get('name')
    product_url = request.json.get('url')
    
    # Check if product_url is already present in user_search_history
    for entry in user_search_history:
        print("a")
        if entry['product_url'] == product_url:
            return jsonify({'message': 'Product URL already present in search history'})
        

    # If product_url is not present, add it to user_search_history
    user_search_history.append({
        'search_term': search_term,
        'product_url': product_url
    })

    return jsonify({'message': 'Search history saved successfully'})


def generate_prompt(data):
    prompt = f"""Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction: 

# Your task is to generate a structured summary based on the provided reviews
# Use the following template to structure the information:
# Dont't use same aspect in pros and cons generation and don't repeat the peos and
# Pros:
# - Aspect: [Performance/Build Quality/Price-Value Ratio/Ease of Use]
#   - Positive feedback: [Percentage] of users expressed satisfaction.
#   - Reasons: Mention what users liked about this aspect.
# Cons:
# - Aspect: [Noise/Plastic Quality/Price/Shaking During Operation]
#   - Negative feedback: [Percentage] of users expressed dissatisfaction.
#   - Reasons: Mention the specific issues users had with this aspect.

# Your code should process the 'reviews' input and generate a summary in this structured format. Ensure that you calculate the percentages of user satisfaction or dissatisfaction based on the reviews.
# Reviews
{data}

### Response:
"""
    return prompt


def generate_question_prompt(response, question):
    prompt = f"""Use the following pieces of information to answer the user's question. If you don't know the answer, just say that you don't know, don't try to make up an answer.
### Context: {response}
### Question: {question}
Only return the helpful answer below and nothing else, and please be precise while answering the question.
### Response:
"""
    return prompt

@app.route('/api/ask_question', methods=['POST'])
def ask_question():
    start = time.time()
    
    summary = request.json['summary']
    question = request.json['question']
    
    prompt = generate_question_prompt(summary,question)
    response = get_response(prompt).replace('</s>', '').replace('\n', '')
    
    end = time.time()
    resp = jsonify({
        'question': question,
        'answer': response,
        'execution_time': f"{(end - start)} seconds"
    })
    resp.status_code = 200
    return resp

@app.route('/api/generate_summary', methods=['POST'])
def generate_summary():
    start = time.time()
   
  
    print(request.json)
    print(request.data)

    product_link = request.json['product_link']
    
    print(product_link)
    with open('reviews.json', 'r') as file:
      data = json.load(file)
    reviews = list(data['Reviews'])
    reviews_list = []
    token_size = 0
    reviews_list.append(reviews['product_details'])
    # Collect reviews until the token limit is reached
    for each_review in reviews:
        if token_size < 2048:
            reviews_list.append(each_review['content'])
            token_size += len(each_review['content'])
        else:
            break
    product_name = data['name']
    img_url = data['img_url']
    URL=data['URL']
    user_search_history.append({
        'search_term': product_name,
        'product_url': URL
    })
    prompt = generate_prompt(reviews_list)
    response_text=get_response(prompt).replace('</s>', '').replace('\n', '').replace("Aspect X:", "\n-")
    
    
   

 # Use regular expressions to extract Pros and Cons
    pros_match = re.search(r'Pros:(.*?)Cons:', response_text, re.DOTALL)
    cons_match = re.search(r'Cons:(.*?)Overall,', response_text, re.DOTALL)
        
    if pros_match:
            pros = pros_match.group(1).strip()
    else:
            pros = "Pros not Found"
    
    if cons_match:
            cons = cons_match.group(1).strip()
    else:
            cons = "Cons not found"
    
    pros_list = []
    cons_list = []
    
    if pros_match:
            pros_text = pros_match.group(1).strip()
            pros_list = [line.strip() for line in pros_text.split('\n') if line.strip()]
        
    if cons_match:
            cons_text = cons_match.group(1).strip()
            cons_list = [line.strip() for line in cons_text.split('\n') if line.strip()]
        
        # Iterate through responseProsList and print each key term
    responseProsList_bold = []
    for item in pros_list:
     if ':' in item:
        key_term, rest_of_text = item.split(':', 1)  # Split at the first colon to separate key term and the rest of the text
        bold_key_term_pros = f"<b>{key_term.strip()}:</b>"  # Wrap the key term with bold tags
        responseProsList_bold.append(bold_key_term_pros + rest_of_text)
     else:
        responseProsList_bold.append(item) 
    responseConsList_bold = []
    for item in cons_list:
     if ':' in item:
        key_term, rest_of_text = item.split(':', 1)  # Split at the first colon to separate key term and the rest of the text
        bold_key_terms_cons = f"<b>{key_term.strip()}:</b>"  # Wrap the key term with bold tags
        responseConsList_bold.append(bold_key_terms_cons + rest_of_text)
     else:
        responseConsList_bold.append(item) 



    end = time.time()
    resp = jsonify({
    'execution_time': f"{(end - start)} seconds",
    'response': response_text,
    'img_url': img_url,
    'product_name': product_name,
    'responsePros': pros,
    'responseCons': cons,
    'responseProsList':responseProsList_bold,
    'responseConsList':responseConsList_bold
    
     })
    
    resp.status_code = 200

    return resp
@app.route('/api/given_url',methods=['POST'])
def get_link():
    try:
        data = request.get_json()  # Get JSON data from the request body
        url = data.get('url')  # Extract the URL from the JSON data

        if url:
            # Call your flipkart function with the provided URL
            flipkart(url, num_pages=5)
            return jsonify({"message": "Data scraped and saved as reviews.json"}), 200
        else:
            # Return an error response if the URL is missing
            return jsonify({"error": "Invalid URL"}), 400
    except Exception as e:
        # Handle any exceptions that might occur during processing
        return jsonify({"error": str(e)}), 500

# Example usage:
if __name__ == "__main__":
    # product_url = "https://www.flipkart.com/realme-11x-5g-purple-dawn-128-gb/p/itm07be1a2ff1a1b?pid=MOBGS2W3YT99HRJ4&lid=LSTMOBGS2W3YT99HRJ4VJBEQO&marketplace=FLIPKART&store=tyy%2F4io&srno=b_1_1&otracker=nmenu_sub_Electronics_0_Realme&fm=organic&iid=450829f6-97d6-4bf6-aaee-7557f103217d.MOBGS2W3YT99HRJ4.SEARCH&ppt=clp&ppn=poco-c65-coming-soon-store&ssid=tdqyfq9pxs0000001702364851160"
    # product_data = flipkart(product_url, num_pages=5)
    app.run(host="0.0.0.0", port=5003, debug=True, use_reloader=False)
    # print(product_data)
