import time
import threading
from sqlalchemy import text
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.types import Enum as SqlEnum
import enum

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/parking'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

last_detected_plate = None
grab_license_plate = False


class ParkingType(enum.Enum):
    DEFAULT = "DEFAULT"
    MANAGER = "MANAGER"
    DISABLED = "DISABLED"
    EXIT = "EXIT"
    ROAD = "ROAD"
    ENTRANCE = "ENTRANCE"
    EXITV2 = "EXITV2"


# MODELE
class AllowedLicensePlate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(50), nullable=False)
    parking_type = db.Column(SqlEnum(ParkingType, name="parking_type_enum"), nullable=False)


class CarsOnParking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(50), nullable=False, unique=True)
    entry_timestamp = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class CarPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(50), nullable=False, unique=True)  # Make license_plate unique
    center_x = db.Column(db.Integer, nullable=False)
    center_y = db.Column(db.Integer, nullable=False)
    left_top_x = db.Column(db.Integer, nullable=False)
    left_top_y = db.Column(db.Integer, nullable=False)
    right_bottom_x = db.Column(db.Integer, nullable=False)
    right_bottom_y = db.Column(db.Integer, nullable=False)


class ParkingArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    top_left_x = db.Column(db.Integer, nullable=False)
    top_left_y = db.Column(db.Integer, nullable=False)
    bottom_right_x = db.Column(db.Integer, nullable=False)
    bottom_right_y = db.Column(db.Integer, nullable=False)
    parking_type = db.Column(SqlEnum(ParkingType, name="parking_type_enum"), nullable=False)
    license_plate = db.Column(db.String(50), nullable=True)


class Logs(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    type = db.Column(db.String(50), nullable=False)
    log = db.Column(db.String(200), nullable=False)


@app.route('/logs', methods=['GET', 'POST'])
def manage_logs():
    if request.method == 'GET':
        logs = Logs.query.all()
        return jsonify([{
            'id': l.id,
            'timestamp': l.timestamp,
            'type': l.type,
            'log': l.log
        } for l in logs]), 200

    elif request.method == 'POST':
        data = request.json
        log_type = data.get('type')
        log = data.get('log')
        new_log = Logs(type=log_type, log=log)
        db.session.add(new_log)
        db.session.commit()
        return jsonify({'message': 'Log added successfully!'}), 201

# ENDPOINTY
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 420


@app.route('/reset_db', methods=['GET'])
def reset():
    for table in reversed(db.metadata.sorted_tables):
        if table.name != 'allowed_license_plate':
            query = f'DROP TABLE IF EXISTS {table.name}'
            db.session.execute(text(query))
    db.create_all()
    return jsonify({'message': 'Database reset successfully!'}), 200


@app.route('/allowed_license_plates', methods=['GET'])
def get_allowed_license_plates():
    plates = AllowedLicensePlate.query.all()
    return jsonify([{
        'id': p.id,
        'license_plate': p.license_plate,
        'parking_type': p.parking_type.value
    } for p in plates])


@app.route('/parking_areas', methods=['GET', 'POST'])
def manage_parking_areas():
    if request.method == 'GET':
        areas = ParkingArea.query.all()
        return jsonify([{
            'id': a.id,
            'top_left_x': a.top_left_x,
            'top_left_y': a.top_left_y,
            'bottom_right_x': a.bottom_right_x,
            'bottom_right_y': a.bottom_right_y,
            'parking_type': a.parking_type.value
        } for a in areas])

    elif request.method == 'POST':
        data = request.json

        if not isinstance(data, list):
            return jsonify({'error': 'Expected a list of parking areas'}), 400

        for area in data:
            area_id = area.get('id')
            top_left_x = area.get('top_left_x')
            top_left_y = area.get('top_left_y')
            bottom_right_x = area.get('bottom_right_x')
            bottom_right_y = area.get('bottom_right_y')
            parking_type = area.get('type')

            # check if any car is parked in the area
            cars = CarPosition.query.all()
            parked_car = None
            for car in cars:
                if top_left_x <= car.center_x <= bottom_right_x and top_left_y <= car.center_y <= bottom_right_y:
                    parked_car = car
                    break

            if not all([area_id, top_left_x, top_left_y, bottom_right_x, bottom_right_y, parking_type]):
                return jsonify({
                    'error': 'Each parking area must include top_left_x, top_left_y, bottom_right_x, bottom_right_y, and parking_type'}), 400

            existing_area = ParkingArea.query.filter_by(id=area_id).first()

            if existing_area:
                existing_area.top_left_x = top_left_x
                existing_area.top_left_y = top_left_y
                existing_area.bottom_right_x = bottom_right_x
                existing_area.bottom_right_y = bottom_right_y
                existing_area.parking_type = parking_type
                existing_area.license_plate = parked_car.license_plate if parked_car else None

            else:
                new_area = ParkingArea(
                    id=area_id,
                    top_left_x=top_left_x,
                    top_left_y=top_left_y,
                    bottom_right_x=bottom_right_x,
                    bottom_right_y=bottom_right_y,
                    parking_type=parking_type,
                    license_plate=parked_car.license_plate if parked_car else None
                )
                db.session.add(new_area)
            db.session.commit()
        return jsonify({'message': 'Parking areas updated successfully!'}), 201


@app.route('/is_entrance_allowed/<string:license_plate>', methods=['GET'])
def is_allowed(license_plate):
    plate = AllowedLicensePlate.query.filter_by(license_plate=license_plate).first()
    if plate:
        return jsonify({'is_allowed': True, 'parking_type': plate.parking_type.value}), 200
    else:
        return jsonify({'is_allowed': False}), 404


@app.route('/is_parking_allowed/<string:license_plate>/<int:parking_type>', methods=['GET'])
def is_parking_allowed(license_plate, parking_type):
    plate = AllowedLicensePlate.query.filter_by(license_plate=license_plate, parking_type=parking_type).first()
    if plate:
        return jsonify({'is_allowed': True}), 200
    else:
        return jsonify({'is_allowed': False}), 404


@app.route('/is_car_out_of_entrance', methods=['GET'])
def is_car_out_of_entrance():
    car = CarsOnParking.query.order_by(CarsOnParking.entry_timestamp.desc()).first()
    if not car:
        return jsonify({'is_out': True}), 200

    entrance_area = ParkingArea.query.filter_by(parking_type=ParkingType.ENTRANCE).first()

    if entrance_area.license_plate != car.license_plate:
        return jsonify({'is_out': True}), 200
    else:
        return jsonify({'is_out': False}), 200


@app.route('/car_entrance', methods=['GET', 'POST', 'DELETE'])
def manage_cars_on_parking():
    if request.method == 'GET':
        cars = CarsOnParking.query.all()
        return jsonify(
            [{'id': c.id, 'license_plate': c.license_plate, 'entry_timestamp': c.entry_timestamp} for c in cars])

    elif request.method == 'POST':
        data = request.json
        # check if car is not already on parking
        car = CarsOnParking.query.filter_by(license_plate=data['license_plate']).first()
        if car:
            return jsonify({'error': 'Car already on parking'}), 400
        new_car = CarsOnParking(license_plate=data['license_plate'])
        db.session.add(new_car)
        db.session.commit()
        return jsonify({'message': 'Car entry logged successfully!'}), 201


@app.route('/car_position', methods=['GET', 'POST'])
def manage_car_position():
    if request.method == 'GET':
        positions = CarPosition.query.all()
        return jsonify([{
            'id': p.id,
            'license_plate': p.license_plate,
            'center_x': p.center_x,
            'center_y': p.center_y,
            'left_top_x': p.left_top_x,
            'left_top_y': p.left_top_y,
            'right_bottom_x': p.right_bottom_x,
            'right_bottom_y': p.right_bottom_y
        } for p in positions]), 200

    elif request.method == 'POST':
        data = request.json
        data = [data] if not isinstance(data, list) else data
        for position in data:
            license_plate = position.get('license_plate')
            center_x = position.get('center_x')
            center_y = position.get('center_y')
            left_top_x = position.get('left_top_x')
            left_top_y = position.get('left_top_y')
            right_bottom_x = position.get('right_bottom_x')
            right_bottom_y = position.get('right_bottom_y')

            if not all([license_plate, center_x, center_y, left_top_x, left_top_y, right_bottom_x, right_bottom_y]):
                return jsonify({
                    'error': 'Each position must include license_plate, center_x, center_y, left_top_x, left_top_y, right_bottom_x, and right_bottom_y'}), 400

            existing_position = CarPosition.query.filter_by(license_plate=license_plate).first()

            # Jeśli istnieje samochód, to zaktualizuj jego pozycję
            if existing_position:
                existing_position.center_x = center_x
                existing_position.center_y = center_y
                existing_position.left_top_x = left_top_x
                existing_position.left_top_y = left_top_y
                existing_position.right_bottom_x = right_bottom_x
                existing_position.right_bottom_y = right_bottom_y

            else:
                new_position = CarPosition(
                    license_plate=license_plate,
                    center_x=center_x,
                    center_y=center_y,
                    left_top_x=left_top_x,
                    left_top_y=left_top_y,
                    right_bottom_x=right_bottom_x,
                    right_bottom_y=right_bottom_y
                )
                db.session.add(new_position)
        db.session.commit()
        return jsonify({'message': 'Positions updated successfully!'}), 201


@app.route('/all_license_plates_positions', methods=['GET'])
def get_all_license_plate_positions():
    cars = CarPosition.query.all()

    if not cars:
        return jsonify({'error': 'No cars detected'}), 404

    # Collect all car positions and license plates
    car_positions = [
        {
            'license_plate': car.license_plate,
            'center_x': car.center_x,
            'center_y': car.center_y
        }
        for car in cars
    ]
    return jsonify({'cars': car_positions}), 200


@app.route('/are_properly_parked', methods=['GET'])
def is_properly_parked():
    cars = AllowedLicensePlate.query.all()
    if not cars:
        return jsonify({'error': 'No cars detected'}), 401

    parking_areas = ParkingArea.query.where(ParkingArea.license_plate.isnot(None)).all()
    if not parking_areas:
        return jsonify({'error': 'No parking areas defined'}), 401

    improperly_parked_cars = []

    for area in parking_areas:
        car = AllowedLicensePlate.query.filter_by(license_plate=area.license_plate).first()
        if area.parking_type in [ParkingType.ENTRANCE, ParkingType.EXIT, ParkingType.EXITV2, ParkingType.ROAD]:
            continue
        if car.parking_type != area.parking_type:
            improperly_parked_cars.append({
                'license_plate': car.license_plate,
                'expected': car.parking_type.value,
                'actual': area.parking_type.value
            })



    if improperly_parked_cars:
        return jsonify({'is_parked_properly': False, 'improperly_parked_cars': improperly_parked_cars}), 404

    return jsonify({'is_parked_properly': True}), 200


@app.route('/license_plate_from_entrance', methods=['GET', 'POST'])
def get_license_plate_from_entrance():
    global last_detected_plate

    if request.method == 'GET':
        return jsonify({'license_plate': last_detected_plate}), 200

    elif request.method == 'POST':
        data = request.json
        license_plate = data.get('license_plate')

        if not license_plate:
            return jsonify({'error': 'Expected license_plate'}), 400

        last_detected_plate = license_plate
        return jsonify({'message': 'License plate added successfully!'}), 201


@app.route('/car_exit/<string:license_plate>', methods=['DELETE'])
def car_exit(license_plate):
    car = CarsOnParking.query.filter_by(license_plate=license_plate).first()
    if not car:
        return jsonify({'error': 'Car not found'}), 404
    db.session.delete(car)
    car_position = CarPosition.query.filter_by(license_plate=license_plate).first()
    if car_position:
        db.session.delete(car_position)
    db.session.commit()
    return jsonify({'message': 'Car exited successfully!'}), 200


@app.route('/last_registered_license_plate', methods=['GET'])
def last_registered_license_plate():
    last_car = CarsOnParking.query.order_by(CarsOnParking.entry_timestamp.desc()).first()
    if last_car:
        return jsonify({'license_plate': last_car.license_plate}), 200
    else:
        return jsonify({'license_plate': None}), 404


@app.route('/license_plate_from_exit', methods=['GET'])
def get_license_plate_from_exit():
    exit_area = ParkingArea.query.filter_by(parking_type=ParkingType.EXIT).first()
    if exit_area.license_plate:
        return jsonify({'license_plate': exit_area.license_plate}), 200
    else:
        return jsonify({'license_plate': None}), 404


@app.route('/takes_one_slot',methods=['GET'])
def take_one_slot_check():
    parking_areas = ParkingArea.query.where(ParkingArea.license_plate.isnot(None)).all()
    if not parking_areas:
        return jsonify({'error': 'No parking areas defined'}), 401

    improperly_parked_cars = []

    for area in parking_areas:
        car = CarPosition.query.filter_by(license_plate=area.license_plate).first()
        if area.parking_type in [ParkingType.ENTRANCE, ParkingType.EXIT, ParkingType.EXITV2, ParkingType.ROAD]:
            continue
        if car.left_top_x > area.top_left_x and car.left_top_y > area.left_top_y and car.right_bottom_x < area.bottom_right_x and car.right_bottom_y < area.bottom_right_y:
            improperly_parked_cars.append(car.license_plate)

    if improperly_parked_cars:
        return jsonify({'improperly_parked_cars': improperly_parked_cars}), 200
    else:
        return jsonify({'improperly_parked_cars': None}), 404

if __name__ == '__main__':
    app.run(debug=True)
