from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import mercadopago
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')  # <- Pega do ambiente
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///usuarios.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Usa token seguro vindo das variáveis de ambiente
sdk = mercadopago.SDK(os.environ.get("MERCADO_PAGO_TOKEN"))

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    senha = db.Column(db.String(150))
    tem_assinatura = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "").strip()
        if not email or not senha:
            flash("Email e senha são obrigatórios.", "danger")
            return redirect(url_for("registrar"))
        if Usuario.query.filter_by(email=email).first():
            flash("Email já cadastrado.", "danger")
            return redirect(url_for("registrar"))
        novo_usuario = Usuario(email=email, senha=senha)
        db.session.add(novo_usuario)
        db.session.commit()
        flash("Registro feito com sucesso! Faça login.", "success")
        return redirect(url_for("login"))
    return render_template("registrar.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "").strip()
        usuario = Usuario.query.filter_by(email=email).first()
        if not usuario:
            flash("Email não encontrado.", "danger")
            return render_template("login.html")
        if usuario.senha != senha:
            flash("Senha incorreta.", "danger")
            return render_template("login.html")
        login_user(usuario)
        return redirect(url_for("area_premium"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/area-premium")
@login_required
def area_premium():
    if not current_user.tem_assinatura:
        flash("Você precisa assinar o serviço premium para acessar esta área.", "warning")
        return redirect(url_for("comprar"))
    return render_template("premium.html")

@app.route("/comprar")
@login_required
def comprar():
    base_url = request.host_url.rstrip('/')

    preference_data = {
        "items": [{
            "title": "Assinatura Premium Mensal",
            "description": "Acesso completo à área premium por 30 dias",
            "quantity": 1,
            "currency_id": "BRL",
            "unit_price": 15.0
        }],
        "payer": {
            "email": current_user.email
        },
        "payment_methods": {
            "excluded_payment_types": [{"id": "ticket"}],
            "installments": 1
        },
        "back_urls": {
            "success": f"{base_url}/pagamento_sucesso",
            "failure": f"{base_url}/pagamento_erro",
            "pending": f"{base_url}/pagamento_pendente"
        },
        "auto_return": "approved",
        "notification_url": f"{base_url}/notificacao",
        "external_reference": str(current_user.id),
        "statement_descriptor": "PREMIUMASSINATURA"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        if preference_response["status"] in [200, 201]:
            return redirect(preference_response["response"]["init_point"])
        else:
            app.logger.error(f"Erro no Mercado Pago: {preference_response}")
            flash("Erro ao iniciar pagamento. Tente novamente mais tarde.", "danger")
            return render_template("premium.html")
    except Exception as e:
        app.logger.error(f"Exceção no pagamento: {str(e)}")
        flash("Erro inesperado. Por favor, tente novamente.", "danger")
        return render_template("premium.html")

@app.route("/pagamento_sucesso")
@login_required
def pagamento_sucesso():
    usuario = db.session.get(Usuario, current_user.id)
    usuario.tem_assinatura = True
    db.session.commit()
    flash("Pagamento aprovado com sucesso! Bem-vindo à área premium.", "success")
    return redirect(url_for("area_premium"))

@app.route("/pagamento_erro")
@login_required
def pagamento_erro():
    flash("Houve um problema com seu pagamento. Por favor, tente novamente.", "danger")
    return redirect(url_for("comprar"))

@app.route("/pagamento_pendente")
@login_required
def pagamento_pendente():
    flash("Seu pagamento está sendo processado. Você receberá um e-mail quando for confirmado.", "warning")
    return redirect(url_for("area_premium"))

@app.route("/notificacao", methods=["POST"])
def notificacao():
    try:
        payment_id = request.form.get("data.id")
        if payment_id:
            payment_info = sdk.payment().get(payment_id)
            if payment_info["status"] == 200:
                payment = payment_info["response"]
                if payment["status"] == "approved":
                    user_id = int(payment["external_reference"])
                    usuario = db.session.get(Usuario, user_id)
                    if usuario and not usuario.tem_assinatura:
                        usuario.tem_assinatura = True
                        db.session.commit()
        return "", 200
    except Exception as e:
        app.logger.error(f"Erro na notificação: {str(e)}")
        return "", 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
