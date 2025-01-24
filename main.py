import time
import numpy as np
import cv2
from sqlalchemy.sql.sqltypes import NULLTYPE

from ultralytics import YOLO
from paddleocr import PaddleOCR

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.types import Enum as SqlEnum
import enum

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/parking'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

last_detected_plate = None


class ParkingType(enum.Enum):
    DEFAULT = "DEFAULT"
    MANAGER = "MANAGER"
    DISABLED = "DISABLED"
    EXIT = "EXIT"
    ROAD = "ROAD"
    ENTRANCE = "ENTRANCE"


# MODELE
class AllowedLicensePlate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False)
    parking_type = db.Column(SqlEnum(ParkingType, name="parking_type_enum"), nullable=False)


class CarsOnParking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False, unique=True)
    entry_timestamp = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class CarPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String, nullable=False)
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
    license_plate = db.Column(db.String, db.ForeignKey('car_position.license_plate'), nullable=True)


# ENDPOINTY
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 420


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
    print(license_plate)
    plate = AllowedLicensePlate.query.filter_by(license_plate=license_plate).first()
    print(plate)
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
        new_car = CarsOnParking(license_plate=data['license_plate'])
        db.session.add(new_car)
        db.session.commit()
        return jsonify({'message': 'Car entry logged successfully!'}), 201

    elif request.method == 'DELETE':
        data = request.json
        car = CarsOnParking.query.filter_by(license_plate=data['license_plate']).first()
        if car:
            db.session.delete(car)
            db.session.commit()
            return jsonify({'message': 'Car exit logged successfully!'}), 200
        else:
            return jsonify({'error': 'Car not found'}), 404


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

        if not isinstance(data, list):
            return jsonify({'error': 'Expected a list of positions'}), 400

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


@app.route('/license_plate_by_position/<int:center_x>/<int:center_y>', methods=['GET'])
def get_license_plate_by_position(center_x, center_y):
    cars = CarPosition.query.all()
    if len(cars) == 0:
        return jsonify({'error': 'No cars detected'}), 404
    distances = []
    for car in cars:
        distances.append((car.license_plate, np.sqrt((center_x - car.center_x) ** 2 + (center_y - car.center_y) ** 2)))
    closest_car = min(distances, key=lambda x: x[1])
    return jsonify({'license_plate': closest_car[0]}), 200


@app.route('/is_properly_parked/<string:license_plate>', methods=['GET'])
def is_properly_parked(license_plate):
    car = CarPosition.query.filter_by(license_plate=license_plate).first()
    parking_area = ParkingArea.query.filter_by(license_plate=car.license_plate).first()
    car_parking_type = AllowedLicensePlate.query.filter_by(license_plate=car.license_plate).first().parking_type

    parking_area_boundary = (
        parking_area.top_left_x, parking_area.top_left_y, parking_area.bottom_right_x, parking_area.bottom_right_y)
    car_boundary = (car.left_top_x, car.left_top_y, car.right_bottom_x, car.right_bottom_y)

    if car_parking_type.value != parking_area.parking_type.value:
        return jsonify({'is_properly_parked': False, 'reason': 'wrong_permission'}), 404

    if parking_area_boundary[0] <= car_boundary[0] and parking_area_boundary[1] <= car_boundary[1] and \
            parking_area_boundary[2] >= car_boundary[2] and parking_area_boundary[3] >= car_boundary[3]:
        return jsonify({'is_properly_parked': True})
    else:
        return jsonify({'is_properly_parked': False, 'reason': 'not_in_proper_boundaries'}), 404


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


if __name__ == '__main__':
    app.run(debug=True)
