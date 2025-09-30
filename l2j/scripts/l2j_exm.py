import os
import requests
from bs4 import BeautifulSoup
import re
import json
import subprocess
import shlex


def link2json(filename, url):
    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        target_script = soup.body.find('div').find('script')

        if target_script and target_script.string:
            script_content = target_script.string

            match = re.search(
                r'kit\.start\([\s\S]*?(\{\s*node_ids[\s\S]*?\})\s*\);',
                script_content
            )

            if match:
                text = match.group(1)

                first_end = text.find("\n")
                second_end = text.find("\n", first_end + 1)

                idx1 = text.rfind("\n")
                idx2 = text.rfind("\n", 0, idx1)
                idx3 = text.rfind("\n", 0, idx2)

                middle = text[second_end + 1:idx3].split("\n")
                middle = "\n".join(middle).lstrip()[:-1]

                with open('k', "w") as f:
                    f.write(middle)

                safe_filename = shlex.quote(filename)

                cmd = (
                    f'node -e "console.log(JSON.stringify('
                        f"eval(require('fs').readFileSync('k','utf8')), "
                    f"(k,v)=> typeof v==='function' ? v.toString() : v, 2))\""
                )
                p = subprocess.run(cmd, capture_output=True, text=True, shell=True)

                with open(filename, "w") as f:
                    f.write(p.stdout)

            else:
                print("❌ Could not find the data object inside kit.start().")
        else:
            print("❌ Could not find the target script tag at 'body > 1st div > 1st script'.")

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching {url}: {e}")


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


base_url = 'https://questions.examside.com/past-years/jee/bitsat'
sub_json = './subjects.json'

link2json(sub_json, base_url)
with open(sub_json, "r") as f:
    data = json.load(f)

subjects = data[1]["data"]["subjects"]

for subject in subjects:
    sub = subject['key']
    base_dir = f'./{sub}/'
    os.makedirs(base_dir, exist_ok=True)

    sub_divs = subject['chapterGroups']

    for sub_div in sub_divs:
        nm_sub_div = sub_div['key']
        dir_sub_div = f'{base_dir}/{nm_sub_div}/'
        os.makedirs(dir_sub_div, exist_ok=True)
        os.makedirs(f'{dir_sub_div}/raw', exist_ok=True)

        chapters = sub_div["chapters"]
        for chapter in chapters:
            chp_nm = chapter["key"]
            chp_url = f'{base_url}/{sub}/{chp_nm}'
            raw_chp_json = f'{dir_sub_div}/raw/{chp_nm}.json'

            link2json(raw_chp_json, chp_url)
            data = safe_load_json(raw_chp_json)
            if not data:
                continue

            questions = []
            for q in data[1]['data']["questions"][0]['questions']:
                questions.append(q['question']['en'])

            chp_json = f'{dir_sub_div}/{chp_nm}.json'
            with open(chp_json, "w") as f:
                f.write(json.dumps(questions))
