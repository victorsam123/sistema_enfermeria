from flask import Blueprint, redirect, render_template, session, url_for, flash, abort
from flask_login import current_user, login_user, login_required, logout_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.hospital_services.classification import audit as administrative_audit
from app.models import Usuario, utcnow
from app.services import audit, consume_login_attempt, session_fingerprint

bp = Blueprint('auth', __name__)
DUMMY_HASH = generate_password_hash('invalid-placeholder', method='scrypt')


class LoginForm(FlaskForm):
    username = StringField('Usuario', validators=[DataRequired(), Length(max=80)])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(max=256)])


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip().lower()
        if not consume_login_attempt(username):
            audit('limite_intentos')
            db.session.commit()
            return render_template('login.html', form=form, error='Demasiados intentos. Vuelve a intentarlo en 15 minutos.'), 429
        user = db.session.scalar(db.select(Usuario).where(Usuario.username == username).with_for_update())
        valid = check_password_hash(user.password_hash if user else DUMMY_HASH, form.password.data)
        if not valid or not user or not user.activo:
            audit('login_fallido', user)
            db.session.commit()
            return render_template('login.html', form=form, error='Credenciales incorrectas. Verifica tus datos e inténtalo nuevamente.'), 401
        user.ultimo_acceso = utcnow()
        audit('login_exitoso', user)
        administrative_audit('INICIO_SESION', 'usuarios', user.id, user_id=user.id)
        credential_version = session_fingerprint(user)
        db.session.commit()
        session.clear()
        login_user(user, remember=False, fresh=True)
        session['credential_version'] = credential_version
        session.permanent = True
        return redirect(url_for('main.dashboard'))
    return render_template('login.html', form=form)


@bp.post('/logout')
@login_required
def logout():
    audit('logout', current_user)
    administrative_audit('CIERRE_SESION', 'usuarios', current_user.id)
    db.session.commit()
    logout_user()
    session.clear()
    flash('La sesión se cerró correctamente.', 'success')
    return redirect(url_for('auth.login'))
