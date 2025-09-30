import requests
from bs4 import BeautifulSoup
import subprocess
import json
import sys

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



if __name__ == "__main__":
    url = 'https://questions.examside.com/past-years/jee/jee-main/chemistry/thermodynamics'
    output_filename = "extracted_data.json"
    link2json(output_filename,url)
