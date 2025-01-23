from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///parking.db'  # Zmień na swoje ustawienia bazy danych
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELE
class AllowedLicensePlate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False)
    parking_type = db.Column(db.Integer, nullable=False)

class CarOnParking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False)
    entry_timestamp = db.Column(db.DateTime, nullable=False)

class CarPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False)
    center_x = db.Column(db.Integer, nullable=False)
    center_y = db.Column(db.Integer, nullable=False)

# ENDPOINTY
@app.route('/allowed_license_plates', methods=['GET', 'POST'])
def manage_allowed_license_plates():
    if request.method == 'GET':
        plates = AllowedLicensePlate.query.all()
        return jsonify([{'id': p.id, 'license_plate': p.license_plate, 'parking_type': p.parking_type} for p in plates])

    elif request.method == 'POST':
        data = request.json
        new_plate = AllowedLicensePlate(license_plate=data['license_plate'], parking_type=data['parking_type'])
        db.session.add(new_plate)
        db.session.commit()
        return jsonify({'message': 'License plate added successfully!'}), 201

@app.route('/cars_on_parking', methods=['GET', 'POST'])
def manage_cars_on_parking():
    if request.method == 'GET':
        cars = CarOnParking.query.all()
        return jsonify([{'id': c.id, 'license_plate': c.license_plate, 'entry_timestamp': c.entry_timestamp} for c in cars])

    elif request.method == 'POST':
        data = request.json
        new_car = CarOnParking(license_plate=data['license_plate'], entry_timestamp=data['entry_timestamp'])
        db.session.add(new_car)
        db.session.commit()
        return jsonify({'message': 'Car entry logged successfully!'}), 201

@app.route('/car_position', methods=['GET', 'POST'])
def manage_car_position():
    if request.method == 'GET':
        positions = CarPosition.query.all()
        return jsonify([{'id': p.id, 'license_plate': p.license_plate, 'center_x': p.center_x, 'center_y': p.center_y} for p in positions])

    elif request.method == 'POST':
        data = request.json
        new_position = CarPosition(license_plate=data['license_plate'], center_x=data['center_x'], center_y=data['center_y'])
        db.session.add(new_position)
        db.session.commit()
        return jsonify({'message': 'Car position added successfully!'}), 201

# EDYCJA I USUWANIE
@app.route('/allowed_license_plates/<int:id>', methods=['PUT', 'DELETE'])
def modify_allowed_license_plate(id):
    plate = AllowedLicensePlate.query.get_or_404(id)

    if request.method == 'PUT':
        data = request.json
        plate.license_plate = data.get('license_plate', plate.license_plate)
        plate.parking_type = data.get('parking_type', plate.parking_type)
        db.session.commit()
        return jsonify({'message': 'License plate updated successfully!'})

    elif request.method == 'DELETE':
        db.session.delete(plate)
        db.session.commit()
        return jsonify({'message': 'License plate deleted successfully!'})

@app.route('/cars_on_parking/<int:id>', methods=['PUT', 'DELETE'])
def modify_cars_on_parking(id):
    car = CarOnParking.query.get_or_404(id)

    if request.method == 'PUT':
        data = request.json
        car.license_plate = data.get('license_plate', car.license_plate)
        car.entry_timestamp = data.get('entry_timestamp', car.entry_timestamp)
        db.session.commit()
        return jsonify({'message': 'Car entry updated successfully!'})

    elif request.method == 'DELETE':
        db.session.delete(car)
        db.session.commit()
        return jsonify({'message': 'Car entry deleted successfully!'})

@app.route('/car_position/<int:id>', methods=['PUT', 'DELETE'])
def modify_car_position(id):
    position = CarPosition.query.get_or_404(id)

    if request.method == 'PUT':
        data = request.json
        position.license_plate = data.get('license_plate', position.license_plate)
        position.center_x = data.get('center_x', position.center_x)
        position.center_y = data.get('center_y', position.center_y)
        db.session.commit()
        return jsonify({'message': 'Car position updated successfully!'})

    elif request.method == 'DELETE':
        db.session.delete(position)
        db.session.commit()
        return jsonify({'message': 'Car position deleted successfully!'})

if __name__ == '__main__':
    app.run(debug=True)
