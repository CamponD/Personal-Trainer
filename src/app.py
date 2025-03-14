"""
This module takes care of starting the API Server, Loading the DB and Adding the endpoints
"""
import os
from flask import Flask, request, jsonify, url_for, send_from_directory
from flask_migrate import Migrate
from flask_swagger import swagger
from api.utils import APIException, generate_sitemap
from api.models import db, User, Progress, Plan
from api.routes import api
from api.admin import setup_admin
from api.commands import setup_commands
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

load_dotenv()


ENV = "development" if os.getenv("FLASK_DEBUG") == "1" else "production"
static_file_dir = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), '../public/')
app = Flask(__name__)
app.url_map.strict_slashes = False

app.config["JWT_SECRET_KEY"] = os.getenv("JWT_KEY")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 3600
jwt = JWTManager(app)
@jwt.invalid_token_loader
def invalid_token_callback(_):
    return jsonify({'msg': 'Token inválido o mal formado'}), 401

@jwt.expired_token_loader
def expired_token_callback(_,__):
    return jsonify({'msg': 'El token ha expirado. Por favor, inicia sesión nuevamente.'}), 401

@jwt.unauthorized_loader
def unauthorized_callback(_):
    return jsonify({'msg': 'Se requiere un token válido para acceder a este recurso.'}), 401

@jwt.revoked_token_loader
def revoked_token_callback(_, __):
    return jsonify({'msg': 'Este token ha sido revocado.'}), 401

bcrypt = Bcrypt(app)
CORS(app)

# database condiguration
db_url = os.getenv("DATABASE_URL")
if db_url is not None:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace(
        "postgres://", "postgresql://")
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:////tmp/test.db"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
MIGRATE = Migrate(app, db, compare_type=True)
db.init_app(app)

# add the admin
setup_admin(app)

# add the admin
setup_commands(app)

# Add all endpoints form the API with a "api" prefix
app.register_blueprint(api, url_prefix='/api')

# Handle/serialize errors like a JSON object


@app.errorhandler(APIException)
def handle_invalid_usage(error):
    return jsonify(error.to_dict()), error.status_code

# generate sitemap with all your endpoints


@app.route('/')
def sitemap():
    if ENV == "development":
        return generate_sitemap(app)
    return send_from_directory(static_file_dir, 'index.html')

# any other endpoint will try to serve it like a static file
@app.route('/<path:path>', methods=['GET'])
def serve_any_other_file(path):
    if not os.path.isfile(os.path.join(static_file_dir, path)):
        path = 'index.html'
    response = send_from_directory(static_file_dir, path)
    response.cache_control.max_age = 0  # avoid cache memory
    return response

#------------------------------- Users -----------------------------------
@app.route('/register', methods=['POST'])
def new_user():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'msg': 'Debes enviar un body'}), 400

    required_fields = ['email', 'name', 'password']
    missing_fields = [field for field in required_fields if field not in body]
    if missing_fields:
        return jsonify({'msg': f"Faltan los campos: {', '.join(missing_fields)}"}), 400

    if User.query.filter_by(email=body['email']).first():
        return jsonify({'msg': f'El usuario {body["email"]} ya existe'}), 400

    
    new_user = User(
        name = body['name'],
        email = body['email'],
        password = bcrypt.generate_password_hash(str(body['password'])).decode('utf-8')
    )
    db.session.add(new_user)
    db.session.commit()

    user = User.query.filter_by(email=body['email']).first()
    progress = Progress(
        user_id = user.id
    )
    db.session.add(progress)
    db.session.commit()

    return jsonify({'msg': 'Usuario creado'}), 200

@app.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'msg': 'Debes enviar un body'}), 400
    if 'email' not in body:
        return jsonify({'msg': 'Necesitas un email para login'}), 400
    if 'password' not in body:
        return jsonify({'msg': 'Necesitas una contraseña para login'}), 400
    
    user = User.query.filter_by(email=body['email']).first()
    check_password = False
    if user:
        check_password = bcrypt.check_password_hash(user.password, str(body['password']))

    if user is None or check_password is False or user.is_active is False:
        return jsonify({'msg': 'Usario o contraseña no validos'}), 400
    
    access_token = create_access_token(identity=user.email)

    return jsonify({ 'token': access_token, 'role': user.role }), 200

@app.route('/cancel-myself', methods=['GET'])
@jwt_required()
def cancel():
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()

    user.is_active = False
    db.session.commit()

    return jsonify({'msg': "Cliente desactivado."}), 200

@app.route('/cancel-client/<int:client_id>', methods=['GET'])
@jwt_required()
def cancel_client(client_id):
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()

    if user.role != "trainer":
        return jsonify({'msg': 'Usario no autorizado'}), 403
    
    client = User.query.get(client_id)
    if not client:
        return jsonify({'msg': 'Cliente no encontrado'}), 404
    
    client.is_active = False
    db.session.commit()
    
    return jsonify({'Client cancelado': client.serialize()}), 200


@app.route('/private', methods=['GET'])
@jwt_required()
def protected():
    current_user = get_jwt_identity()
    return jsonify({'User': current_user}), 200


@app.route('/my-info', methods=['GET'])
@jwt_required()
def get_info_client():
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()
    progress = Progress.query.filter_by(user_id = user.id).order_by(Progress.date.desc()).first()
    plan = Plan.query.filter_by(user_id = user.id).order_by(Plan.date.desc()).first()

    return jsonify({'Info': user.serialize(), "Progress": progress.serialize(), "Plan": plan.serialize()}), 200


@app.route('/list-clients', methods=['GET'])
@jwt_required()
def get_list_clients():
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()

    if user.role != "trainer":
        return jsonify({'msg': 'Usario no autorizado'}), 403
    
    list_clients = db.session.query(User).filter(User.email != mail_user, User.is_active == True).all()
    result = []
    for user in list_clients:
        result.append({
            "client": user.serialize()
        })

    return jsonify(result), 200


@app.route('/client/<int:client_id>', methods=['GET'])
@jwt_required()
def get_client_info(client_id):
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()

    if user.role != "trainer":
        return jsonify({'msg': 'Usario no autorizado'}), 403
    
    client = User.query.get(client_id)
    if not client:
        return jsonify({'msg': 'Cliente no encontrado'}), 404
    
    progress = Progress.query.filter_by(user_id=client_id).order_by(Progress.date.desc()).first()
    plan = Plan.query.filter_by(user_id=client_id).order_by(Plan.date.desc()).first()
    progress_data = progress.serialize()if progress else None
    plan_data=plan.serialize()if plan else None

    return jsonify({
        'Client': client.serialize(),
        'Progress': progress_data,
        "Plan": plan_data}), 200


@app.route('/profileclient', methods=['GET'])
@jwt_required()
def get_profile(): 
    user_email = get_jwt_identity()
    user = User.query.filter_by(email=user_email).first()

    if not user: 
        return jsonify({'msg':'user not found'}), 404
    
    last_progress = Progress.query.filter_by(user_id = user.id).order_by(Progress.date.desc()).first()
    last_plan = Plan.query.filter_by(user_id = user.id).order_by(Plan.date.desc()).first()
        
    return jsonify({
        'id': user.id,
        'name': user.name,
        'age': user.age,
        'height': str(user.height), 
        'goal': user.goal,
        'goal_kg': user.goal_kg, 
        'progress': {
            'weight': str(last_progress.weight) if last_progress else None, 
            'waist': str(last_progress.waist) if last_progress else None,
            'abdomen': str(last_progress.abdomen) if last_progress else None,
            'arm': str(last_progress.arm) if last_progress else None,
            'leg': str(last_progress.leg) if last_progress else None,
            'progress_percentage':last_progress.progress_percentage if last_progress else None,
            'photo_url': last_progress.photo_url if last_progress else None,
        },
        'plan': {
            'file_url': str(last_plan.file_url) if last_plan else None
        }
            
        })



#------------------------------- Progress -----------------------------------
VALID_GOAL = {'gain', 'lose'}
@app.route('/first-progress', methods=['POST'])
@jwt_required()
def first_progress():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'msg': 'Debes enviar un body'}), 400

    current_user = get_jwt_identity()
    user = User.query.filter_by(email=current_user).first()
    if not user:
        return jsonify({'msg': 'Ususario no encontrado'}), 404

    progress = Progress.query.filter_by(user_id=user.id).first()
    if not progress:
        return jsonify({'msg': 'Progreso inicial no encontrado'}), 404
    
    
    required_fields = ['height', 'weight', 'goal', 'goal_kg']
    missing_fields = [field for field in required_fields if field not in body]
    if missing_fields:
        return jsonify({'msg': f"Faltan los campos: {', '.join(missing_fields)}"}), 400

    try:
        height = float(body['height'])
        weight = float(body['weight'])
        goal = body['goal']
        goal_kg = float(body['goal_kg'])
        if goal not in VALID_GOAL:
            return jsonify ({'msg': f'El objetivo debe ser : {",".join(VALID_GOAL)}'}), 400
        if height <= 0 or weight <= 0 or goal_kg < 0:
            return jsonify ({'msg': 'Los valores de altura peso y kg deben ser mayor que 0'})
        
        user.age = body['age']
        user.height = height
        progress.weight = weight
        user.goal = goal
        user.goal_kg = goal_kg

    except ValueError:
        return jsonify ({'msg': 'Los valores de altura y peso deben ser flotantes y goal_kg un entero'}), 400
    
    optional_fields = ['waist', 'abdomen', 'arm', 'leg']
    for field in optional_fields:
        if field in body:
            try:
                setattr(progress, field, float(body[field]))
            except ValueError:
                return jsonify({'msg': f'El campo {field} debe ser un número válido'}), 400

    progress.photo_url = body.get('photo_url', progress.photo_url)
    progress.notes = body.get('notes', progress.notes)

    try:
        progress.progress_percentage = progress.calculate_progress_percentage()
    except ValueError:
        return jsonify ({'msg': 'Error al calcular el porcentaje de progreso'}), 400

    db.session.commit()

    return jsonify({
        'msg': 'Progreso inicial actualizado',
        'progress_percentage': progress.progress_percentage,
        'weight': progress.weight
    }), 200


@app.route('/new-progress', methods=['POST'])
@jwt_required()
def new_progress():
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({'msg': 'Debes enviar un body'}), 400

    current_user = get_jwt_identity()
    user = User.query.filter_by(email=current_user).first()
    if not user:
        return jsonify({'msg': 'Ususario no encontrado'}), 404
    
    if 'weight' not in body:
        return jsonify({'msg': 'Es necesario el campo peso para registrar un progreso'}), 400

    try:
        new_progress = Progress(
            user_id = user.id,
            weight = float(body['weight'])
        )

        new_progress.user = user
    except ValueError:
        return jsonify({'msg': 'El campo peso debe ser un número válido'}), 400
    
    optional_fields = ['waist', 'abdomen', 'arm', 'leg']
    for field in optional_fields:
        if field in body:
            try:
                setattr(new_progress, field, float(body[field]))
            except ValueError:
                return jsonify({'msg': f'El campo {field} debe ser un número válido'}), 400

    new_progress.photo_url = body.get('photo_url', None)
    new_progress.notes = body.get('notes', None)

    try:
        new_progress.progress_percentage = new_progress.calculate_progress_percentage()
    except ValueError as e:
        return jsonify({'msg': f'Error en los datos: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'msg': f'Error inesperado al calcular el porcentaje: {str(e)}'}), 500

    db.session.add(new_progress)
    db.session.commit()

    return jsonify({
        'msg': 'Progreso actualizado',
        'progress_percentage': new_progress.progress_percentage,
        'weight': new_progress.weight
    }), 200

@app.route('/list-progress/<int:client_id>', methods=['GET'])
@jwt_required()
def get_list_progress(client_id):
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()

    if user.role != "trainer":
        return jsonify({'msg': 'Usario no autorizado'}), 403
    
    progress = db.session.query(Progress).join(User).filter(User.email != mail_user, User.is_active == True, Progress.user_id == client_id).order_by(Progress.date.desc()).first()

    return jsonify(progress.serialize()), 200


app.route('/update-progress', methods = ['POST'])
@jwt_required()
def update_progress():
    user_email = get_jwt_identity()
    user = User.query.filter_by(email=user_email).first()

    if not user:
        return jsonify({'msg': 'Cliente not found'}), 404
    
    data = request.get_json()
    
    new_progress = Progress(
            user_id=user.id,
            weight=float(data.get("weight", 0)),
            waist=float(data.get("waist", 0)),
            abdomen=float(data.get("abdomen", 0)),
            arm=float(data.get("arm", 0)),
            leg=float(data.get("leg", 0)),
            photo_url=data.get("photo_url", None),
            notes=data.get("notes", None)
        )

    new_progress.user = user
    new_progress.progress_percentage = new_progress.calculate_progress_percentage()

    db.session.add(new_progress)
    db.session.commit()

    return jsonify({'msg': 'progresso updated successfull', 'progress': new_progress.serialize()}), 200@app.route('/update-progress', methods = ['POST'])
    



#--------------------------------- Plan -------------------------------------

@app.route('/new-plan', methods=['POST'])
@jwt_required()
def add_plan_client():
    mail_user = get_jwt_identity()
    user = User.query.filter_by(email=mail_user).first()
    body = request.get_json(silent=True)

    if user.role != "trainer":
        return jsonify({'msg': 'Usario no autorizado'}), 403
    
    if body is None:
        return jsonify({'msg': 'Debes enviar un body'}), 400
    if 'user_id' not in body or 'file_url' not in body:
        return jsonify({'msg': 'Es necesario el usuario y la URL del plan'}), 400

    client = User.query.get(body['user_id'])
    if not client:
       return jsonify({'msg': 'Cliente no encontrado'}), 404
    
    new_plan = Plan(
        user_id = client.id,
        file_url = body['file_url'],
        user = client
    )
    new_plan.notes = body.get('notes', None)

    db.session.add(new_plan)
    db.session.commit()

    return jsonify({
        'msg': 'Plan subido',
        'Cliente': client.email,
        'File': new_plan.file_url
    }), 200

    #--------------------------------- Cloudinary -------------------------------------

@app.route('/upload', methods=['POST'])
def upload_file():
    # Verificar si el usuario envió un archivo
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No se ha proporcionado un archivo"}), 400


    try:
        upload_result = cloudinary.uploader.upload(file)
        return jsonify({"url": upload_result["secure_url"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# this only runs if `$ python src/main.py` is executed
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 3001))
    app.run(host='0.0.0.0', port=PORT, debug=True)
