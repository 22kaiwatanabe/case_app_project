# app.py
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import json
import shutil
from werkzeug.utils import secure_filename
import uuid
import tempfile
from pathlib import Path

app = Flask(__name__)
# セキュアなシークレットキー
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['UPLOAD_FOLDER'] = 'uploads/pdfs'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# 許可されたディレクトリのホワイトリスト
ALLOWED_IMPORT_DIRS = [
    r'C:\Users\22kai\Documents',
    r'C:\Users\22kai\Downloads'
]

# データ保存用のJSONファイル
DATA_FILE = 'data/documents.json'

# アップロードディレクトリとデータディレクトリの作成
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('data', exist_ok=True)

# 許可されたファイル拡張子かチェック
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# JSONデータの読み込み
def load_documents():
    if not os.path.exists(DATA_FILE):
        data_dir = os.path.dirname(DATA_FILE)
        if data_dir and not os.path.exists(data_dir): # Ensure data_dir is not empty string
            os.makedirs(data_dir, exist_ok=True)
        return []
    
    if os.path.getsize(DATA_FILE) == 0:
        return []

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            app.logger.error(f"Error decoding JSON from {DATA_FILE}. Returning empty list.")
            return []

# JSONデータの保存
def save_documents(documents):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

def is_safe_path(path):
    """パスが安全かチェック"""
    try:
        resolved_path = Path(path).resolve()
        return any(
            str(resolved_path).startswith(allowed_dir) 
            for allowed_dir in ALLOWED_IMPORT_DIRS
        )
    except (OSError, ValueError):
        return False

def generate_unique_id():
    """一意なIDを生成"""
    return str(uuid.uuid4())

@app.route('/')
def index():
    documents = load_documents()
    # すべてのハッシュタグを収集
    tags = set()
    for doc in documents:
        tags.update(doc.get('tags', []))
    
    # タグでフィルタリング
    filter_tag = request.args.get('tag')
    if filter_tag:
        documents = [doc for doc in documents if filter_tag in doc.get('tags', [])]
    
    return render_template('index.html', documents=documents, tags=sorted(tags))

@app.route('/upload-form')
def upload_form():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('ファイルが選択されていません', 'error')
        return redirect(url_for('upload_form'))
    
    file = request.files['file']
    if file.filename == '':
        flash('ファイルが選択されていません', 'error')
        return redirect(url_for('upload_form'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        
        # Ensure unique filename in upload folder
        base, ext = os.path.splitext(filename)
        counter = 1
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        while os.path.exists(file_path):
            filename = f"{base}_{counter}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            counter += 1
            
        file.save(file_path)
        
        title = request.form.get('title', os.path.splitext(secure_filename(file.filename))[0]) # Use original filename for title default
        description = request.form.get('description', '')
        tags_str = request.form.get('tags', '')
        tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
        
        documents = load_documents()
        documents.append({
            'id': generate_unique_id(), # Use UUID for ID
            'title': title,
            'description': description,
            'filename': filename, # Store the potentially modified unique filename
            'tags': tags
        })
        save_documents(documents)
        
        flash('ファイルのアップロードに成功しました', 'success')
        return redirect(url_for('index'))
    
    flash('許可されていないファイル形式です', 'error')
    return redirect(url_for('upload_form'))

@app.route('/import-folder', methods=['GET', 'POST'])
def import_folder():
    if request.method == 'POST':
        folder_path = request.form.get('folder_path', '').strip()
        
        if not is_safe_path(folder_path):
            flash('指定されたフォルダへのアクセスは許可されていません', 'error')
            return redirect(url_for('import_folder'))
        
        try:
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                flash('指定されたフォルダが存在しないか、フォルダではありません', 'error')
                return redirect(url_for('import_folder'))
            
            pdf_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
            
            if not pdf_files:
                flash('指定されたフォルダにPDFファイルが見つかりませんでした', 'error')
                return redirect(url_for('import_folder'))
            
            documents = load_documents()
            imported_count = 0
            
            for pdf_file_path in pdf_files:
                original_filename = os.path.basename(pdf_file_path)
                secure_name = secure_filename(original_filename)
                
                base, ext = os.path.splitext(secure_name)
                counter = 1
                destination_filename = secure_name
                destination_path = os.path.join(app.config['UPLOAD_FOLDER'], destination_filename)
                
                while os.path.exists(destination_path):
                    destination_filename = f"{base}_{counter}{ext}"
                    destination_path = os.path.join(app.config['UPLOAD_FOLDER'], destination_filename)
                    counter += 1
                
                shutil.copy2(pdf_file_path, destination_path)
                
                tags_str = request.form.get('tags', '')
                tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                
                documents.append({
                    'id': generate_unique_id(), # Use UUID for ID
                    'title': os.path.splitext(original_filename)[0],
                    'description': f"フォルダ '{os.path.basename(folder_path)}' からインポート",
                    'filename': destination_filename, # Store the unique filename
                    'tags': tags
                })
                imported_count += 1
            
            save_documents(documents)
            flash(f'{imported_count}個のPDFファイルをインポートしました', 'success')
            return redirect(url_for('index'))
        
        except PermissionError:
            flash('フォルダへのアクセス権限がありません', 'error')
        except Exception as e:
            app.logger.error(f"Error during folder import: {str(e)}")
            flash(f'インポート中にエラーが発生しました: {str(e)}', 'error')
        
        return redirect(url_for('import_folder'))
    
    return render_template('import_folder.html')

@app.route('/view/<string:doc_id>') # Changed to string:doc_id
def view_document(doc_id):
    documents = load_documents()
    document_to_view = next((doc for doc in documents if doc['id'] == doc_id), None)
    
    if document_to_view:
        return render_template('view.html', document=document_to_view)
    
    flash('ドキュメントが見つかりません', 'error')
    return redirect(url_for('index'))

@app.route('/edit/<string:doc_id>', methods=['GET', 'POST'])
def edit_document(doc_id):
    # TODO: Implement authentication check here - only editors should access
    # if not current_user.is_editor():
    #     flash('この操作を行う権限がありません', 'error')
    #     return redirect(url_for('index'))

    documents = load_documents()
    doc_to_edit = None
    doc_index = -1

    for i, doc in enumerate(documents):
        if doc['id'] == doc_id:
            doc_to_edit = doc
            doc_index = i
            break

    if doc_to_edit is None:
        flash('編集するドキュメントが見つかりません', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form.get('title', doc_to_edit['title']).strip()
        description = request.form.get('description', doc_to_edit['description']).strip()
        tags_str = request.form.get('tags', '')
        tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]

        if not title:
            flash('タイトルは必須です', 'error')
            return render_template('edit_document.html', document=doc_to_edit) # Re-render with error

        documents[doc_index]['title'] = title
        documents[doc_index]['description'] = description
        documents[doc_index]['tags'] = tags
        
        save_documents(documents)
        flash('ドキュメントが更新されました', 'success')
        return redirect(url_for('view_document', doc_id=doc_id))

    return render_template('edit_document.html', document=doc_to_edit)

@app.route('/delete/<string:doc_id>', methods=['POST'])
def delete_document(doc_id):
    # TODO: Implement authentication check here - only editors should access
    # if not current_user.is_editor():
    #     flash('この操作を行う権限がありません', 'error')
    #     return redirect(url_for('index'))

    documents = load_documents()
    doc_to_delete = None
    doc_index = -1

    for i, doc in enumerate(documents):
        if doc['id'] == doc_id:
            doc_to_delete = doc
            doc_index = i
            break

    if doc_to_delete is None:
        flash('削除するドキュメントが見つかりません', 'error')
        return redirect(url_for('index'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc_to_delete['filename'])
        if os.path.exists(file_path):
            os.remove(file_path)
        else:
            app.logger.warning(f"File not found for deletion: {file_path} (Doc ID: {doc_id})")
    except OSError as e:
        app.logger.error(f"Error deleting file {file_path}: {e}")
        flash(f"ファイルの削除中にエラーが発生しました: {e}", 'error')
        # Decide if you want to proceed with DB entry removal or not.
        # For now, we proceed.

    documents.pop(doc_index)
    save_documents(documents)
    
    flash('ドキュメントが削除されました', 'success')
    return redirect(url_for('index'))

@app.route('/pdf/<filename>')
def serve_pdf(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype='application/pdf')

if __name__ == '__main__':
    app.run(debug=True)