import sys
import csv

def analyze(filename):
    print(f"Loading {filename}...")

    times = []
    v_ego = []
    steering_angle = []
    t_driver = []
    t_actuator = []
    gas_pressed = []
    brake_pressed = []
    acc_enabled = []
    lka_active = []

    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            times.append(float(row['time']))
            v_ego.append(float(row.get('v_ego_raw', row.get('v_ego', 0))))
            steering_angle.append(float(row['steering_angle']))
            t_driver.append(float(row['t_driver']))
            t_actuator.append(float(row['t_actuator']))
            gas_pressed.append(str(row['gas_pressed']).lower() == 'true')
            brake_pressed.append(str(row['brake_pressed']).lower() == 'true')
            acc_enabled.append(str(row.get('cruise_enabled', row.get('acc_enabled', 'false'))).lower() == 'true')
            lka_active.append(str(row.get('lda_button', row.get('lka_active', '0'))) != '0' and str(row.get('lda_button', '0')) != 'False')

    if not times:
        print("Empty log file.")
        return

    time_rel = [t - times[0] for t in times]
    max_time = time_rel[-1]

    stats = []
    stats.append("=== EV4 Drive Log Statistics ===")
    stats.append(f"Total Log Time: {max_time:.2f} seconds")
    freq = len(times) / max_time if max_time > 0 else 0
    stats.append(f"Total Data Points: {len(times)} (approx {freq:.1f} Hz)")

    avg_speed = sum(v_ego) / len(v_ego) * 3.6
    max_speed = max(v_ego) * 3.6
    stats.append(f"Average Speed: {avg_speed:.2f} km/h")
    stats.append(f"Max Speed: {max_speed:.2f} km/h")

    stats.append(f"Steering Angle Range: {min(steering_angle):.2f}\u00b0 to {max(steering_angle):.2f}\u00b0")
    stats.append(f"Driver Torque Range: {min(t_driver):.2f} to {max(t_driver):.2f}")
    stats.append(f"Actuator Torque Range: {min(t_actuator):.2f} to {max(t_actuator):.2f}")

    # Calculate durations
    acc_duration = 0
    lka_duration = 0
    gas_duration = 0
    brake_duration = 0

    for i in range(1, len(times)):
        dt = times[i] - times[i-1]
        if acc_enabled[i]: acc_duration += dt
        if lka_active[i]: lka_duration += dt
        if gas_pressed[i]: gas_duration += dt
        if brake_pressed[i]: brake_duration += dt

    stats.append(f"ACC Enabled Duration: {acc_duration:.2f} seconds ({acc_duration/max_time*100:.1f}%)")
    stats.append(f"LKA Active Duration: {lka_duration:.2f} seconds ({lka_duration/max_time*100:.1f}%)")
    stats.append(f"Gas Pedal Pressed: {gas_duration:.2f} seconds")
    stats.append(f"Brake Pedal Pressed: {brake_duration:.2f} seconds")

    stats_str = '\n'.join(stats)

    with open('log_analysis_report.txt', 'w', encoding='utf-8') as f:
        f.write(stats_str)

    print(stats_str)

if __name__ == '__main__':
    filename = sys.argv[1] if len(sys.argv) > 1 else 'ev4_drive_log.csv'
    analyze(filename)
