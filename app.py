import os
import secrets
from pathlib import Path
from threading import RLock

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for

BASE = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
    UPLOAD_FOLDER=BASE / 'uploads',
    PLAYLIST_FILE=BASE / 'playlist.txt',
    MAX_CONTENT_LENGTH=1024 * 1024 * 1024,
    SESSION_COOKIE_SAMESITE='Lax',
)
GRADES = {'all': '공통', '1': '1학년', '2': '2학년', '3': '3학년'}
IMAGES = {'.png', '.jpg', '.jpeg', '.webp'}
VIDEOS = {'.mp4', '.webm', '.mov'}
lock = RLock()


def media_path(name):
    if not name or '/' in name or '\\' in name or name in {'.', '..'}:
        abort(404)
    root = Path(app.config['UPLOAD_FOLDER']).resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        abort(404)
    return candidate


def get_playlist():
    path = Path(app.config['PLAYLIST_FILE'])
    if not path.exists():
        return []
    result = []
    for name in path.read_text(encoding='utf-8').splitlines():
        name = name.strip()
        if name and '/' not in name and '\\' not in name and media_path(name).is_file() and name not in result:
            result.append(name)
    return result


def save_playlist(files):
    path = Path(app.config['PLAYLIST_FILE'])
    temp = path.with_suffix('.tmp')
    temp.write_text(''.join(name + '\n' for name in files), encoding='utf-8')
    temp.replace(path)


@app.context_processor
def template_helpers():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return {'csrf': session['csrf'], 'grades': GRADES}


@app.before_request
def protect_changes():
    if request.method == 'POST':
        expected = session.get('csrf', '')
        if not expected or not secrets.compare_digest(request.form.get('csrf', ''), expected):
            abort(400, '화면을 새로고침한 후 다시 시도해 주세요.')


def item_info(name, position):
    prefix, separator, title = name.partition('_')
    return dict(name=name, title=title if separator else name,
                grade=prefix if prefix in GRADES else 'all',
                kind='image' if Path(name).suffix.lower() in IMAGES else 'video',
                position=position)


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        grade = request.form.get('grade', 'all')
        file = request.files.get('file')
        if grade not in GRADES or not file or not file.filename:
            flash('파일과 송출 대상을 선택해 주세요.', 'error')
            return redirect(url_for('home'))
        raw = file.filename.strip()
        if (not raw or any(c in raw for c in '/\\') or any(ord(c) < 32 for c in raw)
                or Path(raw).suffix.lower() not in IMAGES | VIDEOS):
            flash('PNG, JPG, WEBP 이미지 또는 MP4, WEBM, MOV 영상을 선택해 주세요.', 'error')
            return redirect(url_for('home'))
        with lock:
            root = Path(app.config['UPLOAD_FOLDER'])
            root.mkdir(parents=True, exist_ok=True)
            name = f'{grade}_{raw}'
            number = 2
            while media_path(name).exists():
                name = f'{grade}_{Path(raw).stem} ({number}){Path(raw).suffix}'
                number += 1
            file.save(media_path(name))
            files = get_playlist()
            files.append(name)
            save_playlist(files)
        flash('광고를 추가했어요. 다음 재생 주기부터 화면에 반영됩니다.', 'success')
        return redirect(url_for('home'))
    files = get_playlist()
    items = [item_info(name, i + 1) for i, name in enumerate(files)]
    return render_template('home.html', items=items,
                           image_count=sum(item['kind'] == 'image' for item in items))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    media_path(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/view/<path:filename>')
def view_file(filename):
    if not media_path(filename).is_file():
        abort(404)
    return render_template('view.html', item=item_info(filename, 0))


@app.route('/delete/<path:filename>', methods=['GET', 'POST'])
def delete_file(filename):
    path = media_path(filename)
    if request.method == 'GET':
        if not path.is_file():
            abort(404)
        return render_template('delete.html', item=item_info(filename, 0))
    with lock:
        files = [name for name in get_playlist() if name != filename]
        path.unlink(missing_ok=True)
        save_playlist(files)
    flash('광고를 삭제했어요.', 'success')
    return redirect(url_for('home'))


@app.post('/reorder')
def reorder():
    order = request.form.getlist('order')
    original = request.form.getlist('original')
    with lock:
        files = get_playlist()
        if original != files:
            return jsonify(error='목록이 변경되었어요. 새로고침한 후 다시 시도해 주세요.'), 409
        if len(order) != len(files) or len(set(order)) != len(order) or set(order) != set(files):
            return jsonify(error='올바르지 않은 재생 순서입니다.'), 400
        save_playlist(order)
    return jsonify(ok=True)


@app.get('/display/<grade>')
def display(grade):
    if grade not in GRADES:
        abort(404)
    items = [item_info(name, 0) for name in get_playlist() if Path(name).suffix.lower() in IMAGES | VIDEOS]
    items = [dict(type=item['kind'], src=url_for('uploaded_file', filename=item['name']))
             for item in items if grade == 'all' or item['grade'] in {grade, 'all'}]
    return render_template('display.html', media=items, grade=GRADES[grade])


@app.errorhandler(413)
def too_large(error):
    return '파일은 1GB 이하로 올려 주세요. 뒤로 돌아가 더 작은 파일을 선택해 주세요.', 413


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
