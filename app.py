from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from functools import wraps
import math
import csv
import io
import os

app = Flask(__name__)

# Secret key untuk session & flash
app.config['SECRET_KEY'] = 'kunci-rahasia-aspirasi-mahasiswa-2024-super-secure'

# Konfigurasi database
if os.environ.get('DATABASE_URL'):
    # Railway menyediakan DATABASE_URL otomatis
    database_url = os.environ.get('DATABASE_URL')
    # Fix untuk SQLAlchemy 1.4+ (ubah postgres:// menjadi postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development pakai SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///aspirasi.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi session (kedaluwarsa 2 jam)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

db = SQLAlchemy(app)

# === KREDENSIAL ADMIN (ganti sesuai keinginan) ===
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'  # GANTI dengan password kuat untuk production!

# === MODEL DATABASE ===
class Aspirasi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nomor = db.Column(db.Integer, nullable=False)
    nama = db.Column(db.String(100), nullable=False)
    teks = db.Column(db.Text, nullable=False)
    sentimen = db.Column(db.String(20), default='belum_dilabeli')
    waktu = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'nomor': self.nomor,
            'nama': self.nama,
            'teks': self.teks,
            'sentimen': self.sentimen,
            'waktu': self.waktu.strftime('%Y-%m-%d %H:%M:%S')
        }

    def __repr__(self):
        return f'<Aspirasi {self.nomor}: {self.sentimen}>'

# Buat tabel database
with app.app_context():
    db.create_all()

# === DECORATOR: WAJIB LOGIN ===
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('🔒 Silakan login terlebih dahulu.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# === HELPER FUNCTIONS ===
def get_next_nomor():
    last = Aspirasi.query.order_by(Aspirasi.nomor.desc()).first()
    if last:
        return last.nomor + 1
    return 1

def get_pagination_data(query, page, per_page=10):
    total = query.count()
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    items = query.order_by(Aspirasi.waktu.desc()).offset(offset).limit(per_page).all()
    
    return {
        'items': items,
        'current_page': page,
        'total_pages': total_pages,
        'total': total,
        'per_page': per_page
    }

def get_stats():
    total = Aspirasi.query.count()
    positif = Aspirasi.query.filter_by(sentimen='positif').count()
    negatif = Aspirasi.query.filter_by(sentimen='negatif').count()
    netral = Aspirasi.query.filter_by(sentimen='netral').count()
    belum = Aspirasi.query.filter_by(sentimen='belum_dilabeli').count()
    
    return {
        'total': total,
        'positif': positif,
        'negatif': negatif,
        'netral': netral,
        'belum_dilabeli': belum
    }

# =============================================
# === ROUTES PUBLIK ===
# =============================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/kirim', methods=['POST'])
def kirim():
    nama = request.form.get('nama', '').strip()
    teks = request.form.get('teks', '').strip()

    if not nama:
        nama = 'Anonim'
    
    if not teks:
        flash('❌ Aspirasi tidak boleh kosong!', 'error')
        return redirect(url_for('index'))
    
    if len(teks) < 10:
        flash('❌ Aspirasi minimal 10 karakter!', 'error')
        return redirect(url_for('index'))
    
    if len(teks) > 2000:
        flash('❌ Aspirasi maksimal 2000 karakter!', 'error')
        return redirect(url_for('index'))

    aspirasi_baru = Aspirasi(
        nomor=get_next_nomor(),
        nama=nama,
        teks=teks
    )
    db.session.add(aspirasi_baru)
    db.session.commit()

    flash('✅ Aspirasi berhasil dikirim! Terima kasih.', 'success')
    return render_template('success.html', nama=nama, teks=teks, nomor=aspirasi_baru.nomor)

@app.route('/aspirasi')
@app.route('/aspirasi/<int:page>')
def aspirasi(page=1):
    query = Aspirasi.query
    data = get_pagination_data(query, page, 10)
    return render_template('aspirasi.html', 
                         aspirasi_list=data['items'],
                         current_page=data['current_page'],
                         total_pages=data['total_pages'],
                         total=data['total'])

@app.route('/tentang')
def tentang():
    total_aspirasi = Aspirasi.query.count()
    return render_template('tentang.html', total_aspirasi=total_aspirasi)

# =============================================
# === ROUTES ADMIN ===
# =============================================

@app.route('/admin')
def admin_login():
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login_proses():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        session['admin_username'] = username
        session.permanent = True
        flash('✅ Login berhasil! Selamat datang, Admin.', 'success')
        return redirect(url_for('admin_dashboard'))
    else:
        flash('❌ Username atau password salah!', 'error')
        return redirect(url_for('admin_login'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('👋 Anda telah logout.', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@app.route('/admin/dashboard/<int:page>')
@login_required
def admin_dashboard(page=1):
    # Filter berdasarkan sentimen (jika ada)
    filter_sentimen = request.args.get('sentimen', 'semua')
    search = request.args.get('search', '').strip()
    
    query = Aspirasi.query
    
    if filter_sentimen != 'semua':
        query = query.filter_by(sentimen=filter_sentimen)
    
    if search:
        query = query.filter(
            Aspirasi.teks.contains(search) | Aspirasi.nama.contains(search)
        )
    
    data = get_pagination_data(query, page, 15)
    stats = get_stats()
    
    return render_template('admin/dashboard.html',
                         aspirasi_list=data['items'],
                         current_page=data['current_page'],
                         total_pages=data['total_pages'],
                         total=data['total'],
                         stats=stats,
                         filter_sentimen=filter_sentimen,
                         search=search)

@app.route('/admin/label/<int:aspirasi_id>', methods=['POST'])
@login_required
def label_sentimen(aspirasi_id):
    aspirasi = Aspirasi.query.get_or_404(aspirasi_id)
    sentimen_baru = request.form.get('sentimen', '').strip()
    
    if sentimen_baru in ['positif', 'negatif', 'netral']:
        aspirasi.sentimen = sentimen_baru
        db.session.commit()
        flash(f'✅ Aspirasi #{aspirasi.nomor} berhasil dilabeli sebagai "{sentimen_baru}".', 'success')
    else:
        flash('❌ Sentimen tidak valid!', 'error')
    
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/hapus/<int:aspirasi_id>', methods=['POST'])
@login_required
def hapus_aspirasi(aspirasi_id):
    aspirasi = Aspirasi.query.get_or_404(aspirasi_id)
    nomor = aspirasi.nomor
    db.session.delete(aspirasi)
    db.session.commit()
    flash(f'🗑️ Aspirasi #{nomor} berhasil dihapus.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/export-csv')
@login_required
def export_csv():
    # Ambil hanya yang sudah dilabeli (untuk dataset training)
    sentimen_filter = request.args.get('sentimen', 'semua')
    query = Aspirasi.query
    
    if sentimen_filter != 'semua':
        query = query.filter_by(sentimen=sentimen_filter)
    else:
        # Default: export yang sudah dilabeli saja
        query = query.filter(Aspirasi.sentimen != 'belum_dilabeli')
    
    aspirasi_list = query.order_by(Aspirasi.nomor).all()
    
    # Buat CSV di memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header CSV (format untuk training AI)
    writer.writerow(['nomor', 'nama', 'teks', 'sentimen', 'waktu'])
    
    for a in aspirasi_list:
        writer.writerow([a.nomor, a.nama, a.teks, a.sentimen, a.waktu.strftime('%Y-%m-%d %H:%M:%S')])
    
    output.seek(0)
    
    # Nama file dengan timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'dataset_aspirasi_{timestamp}.csv'
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}'
        }
    )

@app.route('/admin/export-semua-csv')
@login_required
def export_semua_csv():
    """Export semua data termasuk yang belum dilabeli"""
    aspirasi_list = Aspirasi.query.order_by(Aspirasi.nomor).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['nomor', 'nama', 'teks', 'sentimen', 'waktu'])
    
    for a in aspirasi_list:
        writer.writerow([a.nomor, a.nama, a.teks, a.sentimen, a.waktu.strftime('%Y-%m-%d %H:%M:%S')])
    
    output.seek(0)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'semua_aspirasi_{timestamp}.csv'
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}'
        }
    )

# =============================================
# === ERROR HANDLER ===
# =============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', content='''
        <h1>404 - Halaman Tidak Ditemukan</h1>
        <p>Maaf, halaman yang kamu cari tidak ada.</p>
        <a href="/">← Kembali ke Beranda</a>
    '''), 404

# =============================================
# === JALANKAN APLIKASI ===
# =============================================

if __name__ == '__main__':
    app.run(debug=True, port=8080)  # ganti ke 8080