#!/usr/bin/env python3
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

SUBJECTS_DIR = 'subjects'

def get_directories(path):
    try:
        if not os.path.exists(path):
            return []
        
        items = os.listdir(path)
        directories = [item for item in items if os.path.isdir(os.path.join(path, item))]
        return sorted(directories)
    except Exception as e:
        print(f"Error reading directories from {path}: {e}")
        return []

def get_json_files(path):
    try:
        if not os.path.exists(path):
            return []
        
        items = os.listdir(path)
        json_files = [item for item in items if item.endswith('.json') and os.path.isfile(os.path.join(path, item))]
        return sorted(json_files)
    except Exception as e:
        print(f"Error reading JSON files from {path}: {e}")
        return []

def load_questions_from_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        return questions if isinstance(questions, list) else []
    except Exception as e:
        print(f"Error loading questions from {file_path}: {e}")
        return []

def get_all_questions_with_filters(subject_filter=None, division_filter=None, chapter_filter=None):
    all_questions = []
    
    subjects = get_directories(SUBJECTS_DIR)
    
    for subject in subjects:
        if subject_filter and subject != subject_filter:
            continue
            
        subject_path = os.path.join(SUBJECTS_DIR, subject)
        divisions = get_directories(subject_path)
        
        for division in divisions:
            if division_filter and division != division_filter:
                continue
                
            division_path = os.path.join(subject_path, division)
            chapters = get_json_files(division_path)
            
            for chapter in chapters:
                if chapter_filter and chapter != chapter_filter:
                    continue
                    
                chapter_path = os.path.join(division_path, chapter)
                questions = load_questions_from_file(chapter_path)
                
                for index, question in enumerate(questions):
                    if question.get('content'):
                        question_with_meta = {
                            **question,
                            'id': f"{subject}/{division}/{chapter}:{index}",
                            'source': {
                                'subject': subject,
                                'division': division,
                                'chapter': chapter,
                                'index': index
                            }
                        }
                        all_questions.append(question_with_meta)
    
    return all_questions

@app.route('/quiz-enhanced.css')
def serve_css():
    return send_from_directory('.', 'quiz-enhanced.css')

@app.route('/quiz-enhanced.js')
def serve_js():
    return send_from_directory('.', 'quiz-enhanced.js')

@app.route('/quiz-enhanced.html')
def serve_html():
    return send_from_directory('.', 'quiz-enhanced.html')

@app.route('/')
def index():
    return send_from_directory('.', 'quiz-enhanced.html')

@app.route('/static/<path:filename>')
def serve_static_files(filename):
    return send_from_directory('.', filename)

@app.route('/MathJax-master/<path:filename>')
def serve_mathjax(filename):
    return send_from_directory('MathJax-master', filename)

@app.route('/MathJax/<path:filename>')
def serve_mathjax_alias(filename):
    return send_from_directory('MathJax-master', filename)


@app.route('/assets/<path:filename>')
def serve_asset(filename):
    direct_path = os.path.join('assets', filename)
    if os.path.exists(direct_path):
        return send_from_directory('assets', filename)

    for root, dirs, files in os.walk('subjects'):
        candidate = os.path.join(root, filename)
        if os.path.exists(candidate):
            directory = os.path.dirname(candidate)
            filepart = os.path.basename(candidate)
            return send_from_directory(directory, filepart)

    for root, dirs, files in os.walk('subjects'):
        candidate_assets = os.path.join(root, 'assets', filename)
        if os.path.exists(candidate_assets):
            directory = os.path.dirname(candidate_assets)
            filepart = os.path.basename(candidate_assets)
            return send_from_directory(directory, filepart)

    base = os.path.basename(filename)
    for root, dirs, files in os.walk('subjects'):
        if base in files:
            directory = root
            return send_from_directory(directory, base)

    return ('', 404)

@app.route('/<path:prefix>/assets/<path:filename>')
def serve_asset_prefixed(prefix, filename):
    candidate = os.path.join(prefix, 'assets', filename)
    if os.path.exists(candidate):
        directory = os.path.dirname(candidate)
        filepart = os.path.basename(candidate)
        return send_from_directory(directory, filepart)

    candidate2 = os.path.join(SUBJECTS_DIR, prefix, 'assets', filename)
    if os.path.exists(candidate2):
        directory = os.path.dirname(candidate2)
        filepart = os.path.basename(candidate2)
        return send_from_directory(directory, filepart)

    return serve_asset(filename)

@app.route('/favicon.ico')
def favicon():
    if os.path.exists('favicon.ico'):
        return send_from_directory('.', 'favicon.ico')
    return ('', 204)

@app.route('/<subject>/<division>/<chapter>')
def chapter_questions(subject, division, chapter):
    return render_quiz_template(subject=subject, division=division, chapter=chapter)

@app.route('/<subject>/<division>')
def division_questions(subject, division):
    return render_quiz_template(subject=subject, division=division)

@app.route('/<subject>')
def subject_questions(subject):
    return render_quiz_template(subject=subject)

def render_quiz_template(subject=None, division=None, chapter=None):
    filter_params = {}
    if subject:
        filter_params['subject'] = subject
    if division:
        filter_params['division'] = division
    if chapter:
        if not chapter.endswith('.json'):
            chapter = f"{chapter}.json"
        filter_params['chapter'] = chapter
    
    if subject:
        subject_path = os.path.join(SUBJECTS_DIR, subject)
        if not os.path.exists(subject_path):
            return f"Subject '{subject}' not found", 404
    
    if division:
        division_path = os.path.join(SUBJECTS_DIR, subject, division)
        if not os.path.exists(division_path):
            return f"Division '{division}' not found in subject '{subject}'", 404
    
    if chapter:
        chapter_path = os.path.join(SUBJECTS_DIR, subject, division, chapter)
        if not os.path.exists(chapter_path):
            return f"Chapter '{chapter}' not found in {subject}/{division}", 404
    
    try:
        with open('quiz-enhanced.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        zen_flag = 'false'
        zen_param = request.args.get('zen')
        if zen_param and str(zen_param).lower() in ('1', 'true', 'yes', 'on'):
            zen_flag = 'true'

        next_flag = 'false'
        next_param = request.args.get('next')
        if next_param and str(next_param).lower() in ('1', 'true', 'yes', 'on'):
            next_flag = 'true'

        filter_script = f"""
        <script>
        window.urlFilters = {json.dumps(filter_params)};
        window.urlZen = {zen_flag};
        window.urlNext = {next_flag};
        </script>
        """

        html_content = html_content.replace('</head>', f'{filter_script}</head>')

        return html_content
    except Exception as e:
        return f"Error loading quiz template: {str(e)}", 500

@app.route('/api/subjects', methods=['GET'])
def get_subjects():
    subjects = get_directories(SUBJECTS_DIR)
    return jsonify({
        'status': 'success',
        'subjects': subjects
    })

@app.route('/api/subjects/<subject>/divisions', methods=['GET'])
def get_divisions(subject):
    subject_path = os.path.join(SUBJECTS_DIR, subject)
    
    if not os.path.exists(subject_path):
        return jsonify({
            'status': 'error',
            'message': f'Subject "{subject}" not found'
        }), 404
    
    divisions = get_directories(subject_path)
    return jsonify({
        'status': 'success',
        'subject': subject,
        'divisions': divisions
    })

@app.route('/api/subjects/<subject>/<division>/chapters', methods=['GET'])
def get_chapters(subject, division):
    division_path = os.path.join(SUBJECTS_DIR, subject, division)
    
    if not os.path.exists(division_path):
        return jsonify({
            'status': 'error',
            'message': f'Division "{division}" not found in subject "{subject}"'
        }), 404
    
    chapters = get_json_files(division_path)
    return jsonify({
        'status': 'success',
        'subject': subject,
        'division': division,
        'chapters': chapters
    })

@app.route('/api/questions', methods=['GET'])
def get_questions():
    subject = request.args.get('subject')
    division = request.args.get('division')
    chapter = request.args.get('chapter')
    
    try:
        questions = get_all_questions_with_filters(subject, division, chapter)
        
        return jsonify({
            'status': 'success',
            'questions': questions,
            'total': len(questions),
            'filters': {
                'subject': subject,
                'division': division,
                'chapter': chapter
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error loading questions: {str(e)}'
        }), 500

@app.route('/api/question/<subject>/<division>/<chapter>/<int:index>', methods=['GET'])
def get_single_question(subject, division, chapter, index):
    try:
        file_path = os.path.join(SUBJECTS_DIR, subject, division, chapter)
        
        if not os.path.exists(file_path):
            return jsonify({
                'status': 'error',
                'message': 'Question file not found'
            }), 404
        
        questions = load_questions_from_file(file_path)
        
        if index >= len(questions):
            return jsonify({
                'status': 'error',
                'message': 'Question index out of range'
            }), 404
        
        question = questions[index]
        question_with_meta = {
            **question,
            'id': f"{subject}/{division}/{chapter}:{index}",
            'source': {
                'subject': subject,
                'division': division,
                'chapter': chapter,
                'index': index
            }
        }
        
        return jsonify({
            'status': 'success',
            'question': question_with_meta
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error loading question: {str(e)}'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'success',
        'message': 'Enhanced Quiz Application is running',
        'subjects_directory': SUBJECTS_DIR,
        'subjects_available': len(get_directories(SUBJECTS_DIR)),
        'version': '2.0.0'
    })

@app.route('/api/structure', methods=['GET'])
def get_structure():
    structure = {}
    
    try:
        subjects = get_directories(SUBJECTS_DIR)
        
        for subject in subjects:
            structure[subject] = {}
            subject_path = os.path.join(SUBJECTS_DIR, subject)
            divisions = get_directories(subject_path)
            
            for division in divisions:
                division_path = os.path.join(subject_path, division)
                chapters = get_json_files(division_path)
                
                chapter_info = {}
                for chapter in chapters:
                    chapter_path = os.path.join(division_path, chapter)
                    questions = load_questions_from_file(chapter_path)
                    chapter_info[chapter] = {
                        'question_count': len([q for q in questions if q.get('content')])
                    }
                
                structure[subject][division] = chapter_info
        
        total_subjects = len(structure)
        total_divisions = sum(len(divs) for divs in structure.values())
        total_chapters = sum(len(chaps) for subject in structure.values() 
                           for chaps in subject.values())
        total_questions = sum(chap['question_count'] 
                            for subject in structure.values() 
                            for division in subject.values() 
                            for chap in division.values())
        
        return jsonify({
            'status': 'success',
            'structure': structure,
            'summary': {
                'total_subjects': total_subjects,
                'total_divisions': total_divisions,
                'total_chapters': total_chapters,
                'total_questions': total_questions
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error building structure: {str(e)}'
        }), 500

@app.route('/api/state', methods=['POST'])
def save_state():
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            return jsonify({'status': 'error', 'message': 'Invalid state payload'}), 400

        existing = {}
        if os.path.exists('quiz-state.json'):
            try:
                with open('quiz-state.json', 'r', encoding='utf-8') as f:
                    existing = json.load(f) or {}
            except Exception:
                existing = {}

        merged = {}

        existing_attempts = existing.get('attemptedQuestions', {}) or {}
        incoming_attempts = data.get('attemptedQuestions', {}) or {}
        merged_attempts = existing_attempts.copy()
        merged_attempts.update(incoming_attempts)
        merged['attemptedQuestions'] = merged_attempts

        existing_mfr = set(existing.get('markedForReview', []) or [])
        incoming_mfr = set(data.get('markedForReview', []) or [])
        merged['markedForReview'] = sorted(list(existing_mfr.union(incoming_mfr)))

        merged['currentFilter'] = data.get('currentFilter', existing.get('currentFilter', {}))
        merged['currentQuestionIndex'] = data.get('currentQuestionIndex', existing.get('currentQuestionIndex', 0))

        merged['lastUpdated'] = data.get('lastUpdated', existing.get('lastUpdated', datetime.utcnow().isoformat()))
        for key, val in data.items():
            if key not in ('attemptedQuestions', 'markedForReview', 'currentFilter', 'currentQuestionIndex', 'lastUpdated'):
                merged[key] = val

        for key, val in existing.items():
            if key not in merged:
                merged[key] = val

        with open('quiz-state.json', 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        return jsonify({'status': 'success', 'message': 'State merged and saved'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/quiz-state.json', methods=['GET'])
def get_state_file():
    try:
        if os.path.exists('quiz-state.json'):
            return send_from_directory('.', 'quiz-state.json')
        return jsonify({'status': 'error', 'message': 'State file not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Enhanced Quiz Application Server")
    print("=" * 60)
    print(f"📁 Subjects directory: {SUBJECTS_DIR}")
    
    subjects = get_directories(SUBJECTS_DIR)
    print(f"📚 Available subjects: {subjects}")
    
    try:
        total_questions = 0
        for subject in subjects:
            subject_path = os.path.join(SUBJECTS_DIR, subject)
            divisions = get_directories(subject_path)
            subject_questions = 0
            
            for division in divisions:
                division_path = os.path.join(subject_path, division)
                chapters = get_json_files(division_path)
                
                for chapter in chapters:
                    chapter_path = os.path.join(division_path, chapter)
                    questions = load_questions_from_file(chapter_path)
                    valid_questions = len([q for q in questions if q.get('content')])
                    subject_questions += valid_questions
            
            print(f"   • {subject}: {subject_questions} questions")
            total_questions += subject_questions
        
        print(f"📊 Total questions available: {total_questions}")
    except Exception as e:
        print(f"⚠️ Error counting questions: {e}")
    
    print("\n🌐 Available Endpoints:")
    print("   Frontend:")
    print("     • GET / - Main quiz application")
    print("   API:")
    print("     • GET /api/health - Health check")
    print("     • GET /api/subjects - List subjects")
    print("     • GET /api/subjects/{subject}/divisions - List divisions")
    print("     • GET /api/subjects/{subject}/{division}/chapters - List chapters")
    print("     • GET /api/questions?subject=&division=&chapter= - Get filtered questions")
    print("     • GET /api/structure - Complete structure overview")
    
    print(f"\n🎯 Server starting on http://localhost:5000")
    print("   Open this URL in your browser to start using the quiz!")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
