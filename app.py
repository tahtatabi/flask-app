from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import pandas as pd
from datetime import datetime
from urllib.parse import unquote

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Veritabanı Bağlantısı
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Flask-Login Ayarları
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Kullanıcı Modeli
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    process_name = db.Column(db.String(100))
    process_code = db.Column(db.String(50))
    department = db.Column(db.String(50))
    responsible_person = db.Column(db.String(50))
    is_completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    completion_time = db.Column(db.DateTime, nullable=True)  # Yeni sütun

# Veritabanını oluştur
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Ana Sayfa: Departman Kategorileri
@app.route('/')
def index():
    tasks = Task.query.all()
    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.is_completed])
    completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Departman bazında ilerleme yüzdeleri
    department_progress = {}
    users = {}  # Her departmandaki kullanıcıları tutmak için

    for department in {task.department for task in tasks}:
        department_tasks = [task for task in tasks if task.department == department]
        total = len(department_tasks)
        completed = len([task for task in department_tasks if task.is_completed])
        department_progress[department] = (completed / total * 100) if total > 0 else 0

        # Departmandaki benzersiz kullanıcıları topla
        users[department] = list({task.responsible_person for task in department_tasks})

    return render_template(
        'index.html', 
        departments=department_progress, 
        users=users,  # Kullanıcıları şablona gönder
        completion_percentage=completion_percentage
    )


@app.route('/bulk_update/<string:department_name>/<string:user_name>', methods=['POST'])
def bulk_update(department_name, user_name):
    # Sadece belirli kullanıcıya ait görevleri al
    tasks = Task.query.filter_by(department=department_name, responsible_person=user_name).all()

    for task in tasks:
        is_completed_key = f"is_completed_{task.id}"
        notes_key = f"notes_{task.id}"
        if is_completed_key in request.form:
            task.is_completed = True
            if not task.completion_time:  # Sadece tamamlandığında zaman ekle
                task.completion_time = datetime.now()
        else:
            task.is_completed = False
            task.completion_time = None  # Tamamlanma zamanını sıfırla
        task.notes = request.form.get(notes_key, '').strip()

    db.session.commit()
    flash(f"{user_name}'in görevleri başarıyla güncellendi!", "success")
    return redirect(url_for('department_tasks', department_name=department_name, user_name=user_name))



@app.route('/get_users/<string:department_name>')
def get_users(department_name):
    # İlgili departmana ait kişileri al
    tasks = Task.query.filter_by(department=department_name).all()
    users = {task.responsible_person for task in tasks}
    return {"users": list(users)}

# Admin Paneli
@app.route('/admin')
@login_required
def admin():
    tasks = Task.query.all()
    return render_template('admin.html', tasks=tasks)

# Görev Silme
@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_task(id):
    task = Task.query.get(id)
    if task:
        db.session.delete(task)
        db.session.commit()
        flash('Görev başarıyla silindi.', 'success')
    else:
        flash('Görev bulunamadı.', 'danger')
    return redirect(url_for('admin'))

# Tüm Görevleri Silme
@app.route('/delete_all', methods=['POST'])
@login_required
def delete_all_tasks():
    db.session.query(Task).delete()
    db.session.commit()
    flash('Tüm görevler başarıyla silindi.', 'success')
    return redirect(url_for('admin'))

# Görev Düzenleme
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    task = Task.query.get(id)
    if request.method == 'POST':
        task.process_name = request.form['process_name']
        task.process_code = request.form['process_code']
        task.department = request.form['department']
        task.responsible_person = request.form['responsible_person']
        task.is_completed = 'is_completed' in request.form
        task.notes = request.form['notes']
        db.session.commit()
        flash('Görev başarıyla güncellendi.', 'success')
        return redirect(url_for('admin'))
    return render_template('edit_task.html', task=task)

# Excel Dosyası Güncelleme
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('Dosya yüklenmedi!', 'danger')
        return redirect(url_for('admin'))
    file = request.files['file']
    if file.filename == '':
        flash('Dosya seçilmedi!', 'danger')
        return redirect(url_for('admin'))

    df = pd.read_excel(file)
    for _, row in df.iterrows():
        new_task = Task(
            process_name=row['İşlem'],
            process_code=row['İşlem Kodu'],
            department=row['Departman'],
            responsible_person=row['Sorumlu Kişi']
        )
        db.session.add(new_task)
    db.session.commit()
    flash('Excel dosyası başarıyla güncellendi!', 'success')
    return redirect(url_for('admin'))

@app.route('/update_task/<int:id>', methods=['POST'])
def update_task(id):
    task = Task.query.get(id)
    if task:
        task.is_completed = 'is_completed' in request.form
        task.notes = request.form.get('notes', '').strip()
        db.session.commit()
        flash('Görev başarıyla güncellendi.', 'success')
    else:
        flash('Görev bulunamadı.', 'danger')
    return redirect(request.referrer)

# Giriş Yapma
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            return redirect(url_for('admin'))
        flash('Hatalı kullanıcı adı veya şifre!', 'danger')
    return render_template('login.html')

from urllib.parse import unquote

@app.route('/department/<string:department_name>')
def department_tasks(department_name):
    # Kullanıcı adı sorgu parametresinden alınır
    user_name = request.args.get('user')
    if not user_name:
        flash("Kullanıcı belirtilmedi!", "danger")
        return redirect(url_for('index'))

    # Türkçe karakterleri çöz
    department_name = unquote(department_name)
    user_name = unquote(user_name)

    # Görevleri filtrele
    tasks = Task.query.filter_by(department=department_name, responsible_person=user_name).all()

    if not tasks:
        flash(f"{user_name} için {department_name} departmanında görev bulunamadı.", "warning")
        return redirect(url_for('index'))

    total_tasks = len(tasks)
    completed_tasks = len([task for task in tasks if task.is_completed])
    completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return render_template(
        'department_tasks.html',
        tasks=tasks,
        department_name=department_name,
        user_name=user_name,
        completion_percentage=completion_percentage
    )

# Çıkış Yapma
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Başarıyla çıkış yaptınız.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
