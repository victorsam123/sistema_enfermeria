from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import current_user, login_required, login_user
from sqlalchemy.exc import SQLAlchemyError
from app.extensions import db
from app.models import Usuario
from app.services import session_fingerprint, consume_login_attempt
from app.security.passwords import secure_password
from app.security.user_forms import OwnPasswordForm
from app.security.user_operations import user_audit
from app.dashboard_clock import clock_snapshot

bp = Blueprint('account_security', __name__, url_prefix='/mi-cuenta')


@bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def password():
    form = OwnPasswordForm()
    error, status = None, 200
    if form.validate_on_submit():
        if not consume_login_attempt('password:' + current_user.username):
            return render_template('users/password.html', page_title='Cambiar mi contraseña', form=form,
                forced=current_user.debe_cambiar_password, save_error='Demasiados intentos. Vuelve a intentarlo en 15 minutos.', clock=clock_snapshot()), 429
        try:
            target = db.session.scalar(db.select(Usuario).where(Usuario.id == current_user.id).with_for_update().execution_options(populate_existing=True))
            if not target.activo:
                return redirect(url_for('auth.login'), code=303)
            if not target.check_password(form.actual.data):
                form.actual.errors.append('La contraseña actual no es correcta.')
                status = 422
            elif target.check_password(form.password.data):
                form.password.errors.append('La nueva contraseña debe ser diferente a la actual.')
                status = 422
            elif target.username.casefold() in form.password.data.casefold():
                form.password.errors.append('La contraseña no debe contener tu nombre de usuario.')
                status = 422
            else:
                target.set_password(form.password.data)
                target.debe_cambiar_password = False
                user_audit(target, 'PASSWORD_CAMBIADO', 'El titular cambió su contraseña verificando la contraseña actual.')
                db.session.flush()
                db.session.refresh(target)
                credential_version = session_fingerprint(target)
                db.session.commit()
                session.clear()
                login_user(target, remember=False, fresh=True)
                session['credential_version'] = credential_version
                session.permanent = True
                return redirect(url_for('main.dashboard'), code=303)
            db.session.rollback()
        except SQLAlchemyError:
            db.session.rollback()
            error, status = 'No se pudo actualizar la contraseña. Vuelve a intentarlo.', 503
    elif request.method == 'POST':
        status = 422
    return render_template('users/password.html', page_title='Cambiar mi contraseña', form=form,
        forced=current_user.debe_cambiar_password, save_error=error, clock=clock_snapshot()), status


def configure_first_access(app):
    app.register_blueprint(bp)

    @app.before_request
    def enforce_initial_password():
        allowed = {'static', 'auth.login', 'auth.logout', 'account_security.password', 'main.clock', 'main.health'}
        if (request.endpoint and request.endpoint not in allowed and current_user.is_authenticated
                and current_user.debe_cambiar_password):
            return redirect(url_for('account_security.password'), code=303)
