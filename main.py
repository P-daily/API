import time
import numpy as np
import cv2

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
    license_plate = db.Column(db.String, nullable=False)
    entry_timestamp = db.Column(db.DateTime, nullable=False)


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
            top_left_x = area.get('top_left_x')
            top_left_y = area.get('top_left_y')
            bottom_right_x = area.get('bottom_right_x')
            bottom_right_y = area.get('bottom_right_y')
            parking_type = area.get('parking_type')

            if not all([top_left_x, top_left_y, bottom_right_x, bottom_right_y, parking_type.value]):
                return jsonify({
                                   'error': 'Each parking area must include top_left_x, top_left_y, bottom_right_x, bottom_right_y, and parking_type'}), 400

            existing_area = ParkingArea.query.filter_by(top_left_x=top_left_x, top_left_y=top_left_y,
                                                        bottom_right_x=bottom_right_x,
                                                        bottom_right_y=bottom_right_y).first()

            if existing_area:
                existing_area.parking_type.value = parking_type.value

            else:
                new_area = ParkingArea(
                    top_left_x=top_left_x,
                    top_left_y=top_left_y,
                    bottom_right_x=bottom_right_x,
                    bottom_right_y=bottom_right_y,
                    parking_type=parking_type.value
                )
                db.session.add(new_area)
        db.session.commit()
        return jsonify({'message': 'Parking areas updated successfully!'}), 200


@app.route('/is_entrance_allowed/<string:license_plate>', methods=['GET'])
def is_allowed(license_plate):
    plate = AllowedLicensePlate.query.filter_by(license_plate=license_plate).first()
    if plate:
        return jsonify({'is_allowed': True, 'parking_type': plate.parking_type.value})
    else:
        return jsonify({'is_allowed': False}), 404


@app.route('/is_parking_allowed/<string:license_plate>/<int:parking_type>', methods=['GET'])
def is_parking_allowed(license_plate, parking_type):
    plate = AllowedLicensePlate.query.filter_by(license_plate=license_plate, parking_type=parking_type).first()
    if plate:
        return jsonify({'is_allowed': True})
    else:
        return jsonify({'is_allowed': False}), 404


@app.route('/cars_entrance', methods=['GET', 'POST', 'DELETE'])
def manage_cars_on_parking():
    if request.method == 'GET':
        cars = CarsOnParking.query.all()
        return jsonify(
            [{'id': c.id, 'license_plate': c.license_plate, 'entry_timestamp': c.entry_timestamp} for c in cars])

    elif request.method == 'POST':
        data = request.json
        new_car = CarsOnParking(license_plate=data['license_plate'], entry_timestamp=data['entry_timestamp'])
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
        } for p in positions])

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
        return jsonify({'message': 'Positions updated successfully!'}), 200


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


@app.route('/scan', methods=['GET'])
def scan_license_plate():
    ip_camera_url = "http://192.168.0.83:8080/video"
    cap = cv2.VideoCapture(ip_camera_url)

    if not cap.isOpened():
        print("Error: Unable to connect to the IP camera.")
        return jsonify({'error': 'Unable to connect to the IP camera.'}), 500

    # Process every n-th frame
    frame_skip_interval = 10
    frame_count = 0
    last_detection = None
    detection_count = 0

    # Start the timer
    start_time = time.time()
    timeout_seconds = 15

    # Load YOLO model
    model = YOLO("best_plate_detector_model.pt")

    # Initialize PaddleOCR
    ocr = PaddleOCR(use_angle_cls=True, lang='en')

    while True:
        # Check if timeout is reached
        if time.time() - start_time > timeout_seconds:
            print("Timeout reached. No license plate detected.")
            cap.release()
            cv2.destroyAllWindows()
            return jsonify({'error': 'Timeout reached. No license plate detected.'}), 408

        ret, frame = cap.read()  # Capture a frame from the video stream
        if not ret:
            print("Failed to grab frame from IP camera.")
            cap.release()
            cv2.destroyAllWindows()
            return jsonify({'error': 'Failed to grab frame from IP camera.'}), 500

        frame_count += 1
        if frame_count % frame_skip_interval != 0:
            continue

        # Perform inference on the current frame
        results = model(frame)

        # Extract bounding box information
        if results and results[0].boxes:  # Check if any detections exist
            for box in results[0].boxes:  # Iterate over detected boxes
                xyxy = box.xyxy.cpu().numpy()[0]  # Extract coordinates
                x1, y1, x2, y2 = map(int, xyxy)

                # Crop the image using the coordinates
                cropped_img = frame[y1:y2, x1:x2]  # Crop the license plate region


                result = ocr.ocr(cropped_img, cls=True)

                if result and result[0]:
                    detected_text = result[0][0][1][0]

                    if detected_text:
                        if last_detection == detected_text:
                            detection_count += 1
                        else:
                            last_detection = detected_text
                            detection_count = 1

                        # If the same text is detected 5 times, return it
                        if detection_count >= 5:
                            cap.release()
                            cv2.destroyAllWindows()
                            return jsonify({'detected_text': detected_text}), 200

        # Break the loop when the user presses 'Esc'
        if cv2.waitKey(1) & 0xFF == 27:  # 27 is the ASCII code for the 'Esc' key
            break

    cap.release()
    cv2.destroyAllWindows()
    return jsonify({'error': 'No license plate detected.'}), 400


if __name__ == '__main__':
    app.run(debug=True)
