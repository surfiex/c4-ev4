import cereal.messaging as messaging
from opendbc.car.structs import CarState


def debug_engagement():
  sm = messaging.SubMaster(['carState', 'carParams', 'controlsState'])
  print("Starting Engagement Debugger for Kia EV4...")
  print("Press Ctrl+C to stop.\n")

  while True:
    sm.update(100)
    if sm.updated['carState']:
      cs = sm['carState']
      cp = sm['carParams']

      # Engagement Blockers Check
      blockers = []
      if cs.gasPressed:
        blockers.append("Gas Pressed")
      if cs.brakePressed:
        blockers.append("Brake Pressed")
      if cs.doorOpen:
        blockers.append("Door Open")
      if cs.seatbeltUnlatched:
        blockers.append("Seatbelt Unlatched")
      if not cs.cruiseState.available:
        blockers.append("Cruise Not Available")
      if cs.gearShifter != "drive":
        blockers.append(f"Not in Drive ({cs.gearShifter})")
      if cs.steerFaultTemporary:
        blockers.append("Steer Fault (Temp)")
      if cs.steerFaultPermanent:
        blockers.append("Steer Fault (Perm)")

      status = "BLOCKED" if blockers else "READY"

      print(
        f"\rStatus: {status} | Blockers: {', '.join(blockers) if blockers else 'None':<50} | Gear: {cs.gearShifter:<7} | Speed: {cs.vEgo * 3.6:5.1f}km/h",
        end="",
      )

      for event in cs.buttonEvents:
        print(f"\nButton Event: {event.type} Presed: {event.pressed}")


if __name__ == "__main__":
  debug_engagement()
