import cereal.messaging as messaging


def debug_engagement():
  sm = messaging.SubMaster(['carState', 'carParams', 'controlsState'])
  print("Starting Engagement Debugger for Kia EV4 (v2.3)...")
  print("Press Ctrl+C to stop.\n")

  while True:
    sm.update(100)
    if sm.updated['carState']:
      cs = sm['carState']

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
      if str(cs.gearShifter) != "drive":
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
          d = ctrls.to_dict()
          active = d.get('active', d.get('enabled', False))
          state = str(d.get('state', 'N/A'))
        except Exception as e:
          state = f"ERR:{type(e).__name__}"

      status = "ENGAGED" if active else ("READY" if not blockers else "BLOCKED")

      # Raw signals
      raw = f"D:{int(cs.doorOpen)} S:{int(cs.seatbeltUnlatched)} G:{int(cs.gasPressed)} B:{int(cs.brakePressed)} C:{int(cs.cruiseState.available)}"

      # Print line
      print(f"\r{status:<10} | {state:<12} | {raw} | Blockers: {', '.join(blockers) if blockers else 'None':<25} | {cs.vEgo * 3.6:5.1f}km/h", end="")

      # Event logging
      if not hasattr(debug_engagement, 'last_state'):
        debug_engagement.last_state = None
      if debug_engagement.last_state != state:
        if debug_engagement.last_state is not None:
          print(f"\n[EVENT] State: {debug_engagement.last_state} -> {state}")
        debug_engagement.last_state = state

      # Show all buttons that are currently pressed
      for event in cs.buttonEvents:
        if event.pressed:
          print(f"\n[BUTTON] {event.type} Pressed")


if __name__ == "__main__":
  debug_engagement()
