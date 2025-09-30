import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
import json
import subprocess
from typing import Optional, List, Dict
import time
from pathlib import Path
from scraper_config import get_config

class OptimizedScraper:
    def __init__(self, preset: str = 'balanced', **kwargs):
        config = get_config(preset)
        config.update(kwargs)
        
        self.max_concurrent = config['max_concurrent']
        self.delay_between_requests = config['delay_between_requests']
        self.request_timeout = config['request_timeout']
        self.enable_caching = config['enable_caching']
        self.max_retries = config['max_retries']
        self.retry_backoff_factor = config['retry_backoff_factor']
        self.batch_size_multiplier = config['batch_size_multiplier']
        self.user_agent = config['user_agent']
        self.verbose_logging = config['verbose_logging']
        
        print(f"🔧 Using '{preset}' preset: {self.max_concurrent} concurrent, {self.delay_between_requests}s delay")
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cached_files': 0,
            'start_time': None
        }

    async def __aenter__(self):
        config = get_config()
        
        connector = aiohttp.TCPConnector(
            limit=config['connection_pool_size'],
            limit_per_host=config['connections_per_host'],
            ttl_dns_cache=config['dns_cache_ttl'],
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': self.user_agent
            }
        )
        self.stats['start_time'] = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        self.print_stats()

    def should_skip_file(self, filename: str) -> bool:
        if not self.enable_caching:
            return False
        
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            self.stats['cached_files'] += 1
            return True
        return False

    async def link2json_async(self, filename: str, url: str, retries: int = None) -> bool:
        if self.should_skip_file(filename):
            if self.verbose_logging:
                print(f"⚡ Cached: {filename}")
            return True

        if retries is None:
            retries = self.max_retries

        async with self.semaphore:
            for attempt in range(retries):
                try:
                    self.stats['total_requests'] += 1
                    
                    if self.delay_between_requests > 0:
                        await asyncio.sleep(self.delay_between_requests)
                    
                    async with self.session.get(url) as response:
                        response.raise_for_status()
                        html_content = await response.text()

                    soup = BeautifulSoup(html_content, 'html.parser')

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

                            temp_file = f'k_{asyncio.current_task().get_name()}_{int(time.time() * 1000000) % 1000000}'
                            
                            with open(temp_file, "w") as f:
                                f.write(middle)

                            cmd = (
                                f'node -e "console.log(JSON.stringify('
                                    f"eval(require('fs').readFileSync('{temp_file}','utf8')), "
                                f"(k,v)=> typeof v==='function' ? v.toString() : v, 2))\""
                            )
                            
                            os.makedirs(os.path.dirname(filename), exist_ok=True)
                            
                            p = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                            
                            try:
                                os.remove(temp_file)
                            except:
                                pass

                            if p.returncode == 0:
                                with open(filename, "w") as f:
                                    f.write(p.stdout)
                                
                                self.stats['successful_requests'] += 1
                                if self.verbose_logging:
                                    print(f"✅ Success: {filename}")
                                return True
                            else:
                                print(f"⚠️ Node.js processing failed for {url}: {p.stderr}")
                        else:
                            print(f"❌ Could not find data object in {url}")
                    else:
                        print(f"❌ Could not find script tag in {url}")

                except asyncio.TimeoutError:
                    print(f"⏰ Timeout for {url} (attempt {attempt + 1}/{retries})")
                except aiohttp.ClientError as e:
                    print(f"🌐 Network error for {url} (attempt {attempt + 1}/{retries}): {e}")
                except Exception as e:
                    print(f"❌ Unexpected error for {url} (attempt {attempt + 1}/{retries}): {e}")
                
                if attempt < retries - 1:
                    wait_time = (2 ** attempt) * self.retry_backoff_factor
                    await asyncio.sleep(wait_time)

            self.stats['failed_requests'] += 1
            return False

    def safe_load_json(self, path: str) -> Optional[Dict]:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"⚠️ Skipping empty or missing file: {path}")
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ Invalid JSON in file: {path}")
            return None

    def ensure_chapter_groups(self, subject: Dict) -> bool:
        if subject.get("chapterGroups"):
            return False

        chapters = subject.get("chapters")
        if chapters:
            subject["chapterGroups"] = [{
                "title": "All chapters",
                "key": "all",
                "chapters": chapters
            }]
            if "chapters" in subject:
                del subject["chapters"]
            return True

        subject["chapterGroups"] = []
        return False

    def print_stats(self):
        if self.stats['start_time']:
            elapsed = time.time() - self.stats['start_time']
            print(f"\n📊 Scraping Statistics:")
            print(f"   Total time: {elapsed:.2f} seconds")
            print(f"   Total requests: {self.stats['total_requests']}")
            print(f"   Successful: {self.stats['successful_requests']}")
            print(f"   Failed: {self.stats['failed_requests']}")
            print(f"   Cached files: {self.stats['cached_files']}")
            print(f"   Requests/second: {self.stats['total_requests']/elapsed:.2f}")

    async def scrape_all(self):
        root_url = 'https://questions.examside.com'
        main_url = f'{root_url}/past-years'
        exgrps_json = './examgroups.json'
        
        print("🚀 Starting optimized scraping...")
        success = await self.link2json_async(exgrps_json, root_url)
        if not success:
            print("❌ Failed to fetch exam groups")
            return

        exgrps_data = self.safe_load_json(exgrps_json)
        if not exgrps_data:
            return

        exgrps = exgrps_data[0]['data']['nav']['examGroups']
        
        all_tasks = []
        
        for exgrp in exgrps:
            exgrp_nm = exgrp['key']
            os.makedirs(exgrp_nm, exist_ok=True)
            
            for exm in exgrp['exams']:
                exm_nm = exm['key']
                exm_dir = f'{exgrp_nm}/{exm_nm}'
                os.makedirs(exm_dir, exist_ok=True)
                base_url = f'{main_url}/{exm_dir}'
                sub_json = f'{exm_dir}/subjects.json'
                
                all_tasks.append((sub_json, base_url, 'subject'))

        print(f"📚 Processing {len(all_tasks)} subjects concurrently...")
        subject_tasks = [
            self.link2json_async(filename, url) 
            for filename, url, task_type in all_tasks if task_type == 'subject'
        ]
        
        await asyncio.gather(*subject_tasks, return_exceptions=True)
        
        chapter_tasks = []
        
        for exgrp in exgrps:
            exgrp_nm = exgrp['key']
            
            for exm in exgrp['exams']:
                exm_nm = exm['key']
                exm_dir = f'{exgrp_nm}/{exm_nm}'
                base_url = f'{main_url}/{exm_dir}'
                sub_json = f'{exm_dir}/subjects.json'
                
                subjects_data = self.safe_load_json(sub_json)
                if not subjects_data:
                    continue
                
                subjects = subjects_data[1]["data"]["subjects"]
                
                for subject in subjects:
                    sub = subject['key']
                    base_dir = f'{exm_dir}/{sub}/'
                    os.makedirs(base_dir, exist_ok=True)
                    
                    self.ensure_chapter_groups(subject)
                    sub_divs = subject['chapterGroups']
                    
                    for sub_div in sub_divs:
                        nm_sub_div = sub_div['key']
                        dir_sub_div = f'{base_dir}/{nm_sub_div}/'
                        os.makedirs(dir_sub_div, exist_ok=True)
                        os.makedirs(f'{dir_sub_div}/raw', exist_ok=True)
                        
                        if 'chapters' not in sub_div:
                            if self.verbose_logging:
                                print(f"⚠️ No chapters found in sub_div: {nm_sub_div} (skipping)")
                            continue
                        
                        chapters = sub_div["chapters"]
                        for chapter in chapters:
                            chp_nm = chapter["key"]
                            chp_url = f'{base_url}/{sub}/{chp_nm}'
                            raw_chp_json = f'{dir_sub_div}/raw/{chp_nm}.json'
                            
                            chapter_tasks.append({
                                'url': chp_url,
                                'raw_file': raw_chp_json,
                                'final_file': f'{dir_sub_div}/{chp_nm}.json'
                            })

        print(f"📖 Processing {len(chapter_tasks)} chapters concurrently...")
        
        batch_size = self.max_concurrent * self.batch_size_multiplier
        for i in range(0, len(chapter_tasks), batch_size):
            batch = chapter_tasks[i:i + batch_size]
            
            fetch_tasks = [
                self.link2json_async(task['raw_file'], task['url'])
                for task in batch
            ]
            
            await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            for task in batch:
                data = self.safe_load_json(task['raw_file'])
                if not data:
                    continue
                
                try:
                    if (len(data) < 2 or 
                        'data' not in data[1] or 
                        'questions' not in data[1]['data'] or 
                        len(data[1]['data']['questions']) == 0 or
                        'questions' not in data[1]['data']['questions'][0]):
                        if self.verbose_logging:
                            print(f"⚠️ Unexpected data structure in {task['raw_file']} (skipping)")
                        continue
                    
                    questions = []
                    for q in data[1]['data']["questions"][0]['questions']:
                        if 'question' in q and 'en' in q['question']:
                            questions.append(q['question']['en'])
                        else:
                            if self.verbose_logging:
                                print(f"⚠️ Missing question data in {task['raw_file']}")
                    
                    if questions:
                        with open(task['final_file'], "w") as f:
                            json.dump(questions, f)
                    else:
                        if self.verbose_logging:
                            print(f"⚠️ No questions found in {task['raw_file']}")
                        
                except (KeyError, IndexError, TypeError) as e:
                    print(f"⚠️ Error processing questions in {task['raw_file']}: {e}")
            
            print(f"✅ Completed batch {i//batch_size + 1}/{(len(chapter_tasks)-1)//batch_size + 1}")


async def main():
    import sys
    
    preset = 'balanced'
    if len(sys.argv) > 1:
        preset = sys.argv[1]
    
    async with OptimizedScraper(preset=preset) as scraper:
        await scraper.scrape_all()


if __name__ == "__main__":
    asyncio.run(main())
