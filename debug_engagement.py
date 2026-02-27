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

      # Engagement Status
      active = False
      state = "UNKNOWN"
      if sm.updated['controlsState'] or sm.alive['controlsState']:
        ctrls = sm['controlsState']
        try:
          # In some OP versions, this is 'active' or 'enabled'
          active = getattr(ctrls, 'active', getattr(ctrls, 'enabled', False))
          state = str(getattr(ctrls, 'state', 'N/A'))
        except Exception as e:
          state = f"ERR:{type(e).__name__}"
          # Print available attributes once if we error
          if not hasattr(debug_engagement, '_printed_attrs'):
            print(f"\n[DIAG] controlsState attrs: {dir(ctrls)}")
            debug_engagement._printed_attrs = True

      status = "ENGAGED" if active else ("READY" if not blockers else "BLOCKED")

      print(
        f"\rStatus: {status:<8} | State: {state:<12} | Blockers: {', '.join(blockers) if blockers else 'None':<38} | Gear: {str(cs.gearShifter):<7} | Speed: {cs.vEgo * 3.6:5.1f}km/h",
        end="",
      )

      # Show all buttons that are currently pressed
      for event in cs.buttonEvents:
        if event.pressed:
          print(f"\n[BUTTON] {event.type} Pressed")


if __name__ == "__main__":
  debug_engagement()
