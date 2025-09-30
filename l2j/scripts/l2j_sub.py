from os import kill
import os
import requests
from bs4 import BeautifulSoup
import re
import json
import subprocess
def link2json(filename,url):


    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        target_script = soup.body.find('div').find('script')

        if target_script and target_script.string:
            script_content = target_script.string

            
            def trim_text(text):
                pos = -1
                for _ in range(15):
                    pos = text.find("\n", pos + 1)
                    if pos == -1:
                        return ""

                start = pos + 1
                pos = len(text)
                for _ in range(6):
                    pos = text.rfind("\n", 0, pos)
                    if pos == -1:
                        return ""

                end = pos
                return text[start:end].lstrip()[:-1]

            
            if script_content:
                middle = trim_text(script_content)
                open("js1", "w").write(middle)


                cmd = (
                    'node -e "console.log(JSON.stringify('
                        "eval(require('fs').readFileSync('js1','utf8')), "
                        "(k,v)=> typeof v==='function' ? v.toString() : v, 2))\""
                )

                p = subprocess.run(cmd, capture_output=True, text=True, shell=True)

                with open(filename, "w") as f:
                    f.write(p.stdout)

            else:
                print("Could not find the data object inside the kit.start() function call.")
        else:
            print("Could not find the target script tag at 'body > 1st div > 1st script'.")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching the page: {e}")


def safe_load_json(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print(f"⚠️ Skipping empty or missing file: {path}")
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Invalid JSON in file: {path}")
        return None

sub = 'chemistry' 
base_dir = f'./{sub}/'
base_url = f'https://questions.examside.com/past-years/jee/jee-main/{sub}'

os.makedirs(base_dir, exist_ok=True)
sub_json = f'./{sub}/{sub}.json'
link2json(sub_json,base_url)
f = open(sub_json,"r")
data =  json.load(f)


sub_div = data[1]["data"]["subject"]["chapterGroups"]

for i in range(len(sub_div)) :
    nm_sub_div = sub_div[i]['key']
    dir_sub_div = f'{base_dir}/{nm_sub_div}/'
    os.makedirs(dir_sub_div , exist_ok=True)
    os.makedirs(f'{dir_sub_div}/raw', exist_ok=True) 
    chapter = sub_div[i]["chapters"]
    for j in range(len(chapter)): 
        chp_nm = chapter[j]["key"]
        chp_url = f'{base_url}/{chp_nm}'
        raw_chp_json = f'{dir_sub_div}/raw/{chp_nm}.json'
        link2json(raw_chp_json,chp_url)
        data = safe_load_json(raw_chp_json)
        if not data:
            continue
        l = []                                                                          
        chp_json = f'{dir_sub_div}/{chp_nm}.json'
        for x in range(len(data[1]['data']["questions"][0]['questions'])) :              
            l.append(data[1]['data']["questions"][0]['questions'][x]['question']['en'])
        open(chp_json , "w").write(json.dumps(l))
