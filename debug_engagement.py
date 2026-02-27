import cereal.messaging as messaging


def debug_engagement():
  # 0.10.x uses selfdriveState for current engagement state
  services = ['carState', 'controlsState', 'selfdriveState']
  sm = messaging.SubMaster(services)
  print("Starting Engagement Debugger for Kia EV4 (v2.6) [0.10.x Support]...")
  print("Press Ctrl+C to stop.\n")

  last_state = None
  while True:
    sm.update(100)
    if sm.updated['carState']:
      cs = sm['carState']

      # Status logic
      status = "UNKNOWN"
      state = "UNKNOWN"

      # Check for both selfdriveState (0.10.x) and controlsState (legacy)
      msg = None
      if sm.updated.get('selfdriveState') or sm.alive.get('selfdriveState'):
        msg = sm['selfdriveState']
      elif sm.updated.get('controlsState') or sm.alive.get('controlsState'):
        msg = sm['controlsState']

      # Blockers logic (D: Door, S: Seatbelt, G: Gas, B: Brake, C: Cruise)
      raw = f"D:{int(cs.doorOpen)} S:{int(cs.seatbeltUnlatched)} G:{int(cs.gasPressed)} B:{int(cs.brakePressed)} C:{int(cs.cruiseState.available)}"

      blockers = []
      if cs.gasPressed:
        blockers.append("Gas")
      if cs.brakePressed:
        blockers.append("Brake")
      if cs.doorOpen:
        blockers.append("Door")
      if cs.seatbeltUnlatched:
        blockers.append("Seatbelt")
      if not cs.cruiseState.available:
        blockers.append("CruiseOff")

      gear_str = str(cs.gearShifter)
      if "drive" not in gear_str.lower():
        blockers.append(f"Gear:{gear_str}")

      if msg:
        try:
          d = msg.to_dict()
          # Prefer non-deprecated fields, fall back to deprecated ones
          active = d.get('active', d.get('activeDEPRECATED', False))
          state = str(d.get('state', d.get('stateDEPRECATED', 'N/A')))

          if active:
            status = "ENGAGED"
          elif not blockers:
            status = "READY"
          else:
            status = "BLOCKED"
        except Exception as e:
          state = f"ERR:{type(e).__name__}"

      # Print line
      print(f"\r{status:<10} | {state:<15} | {raw} | Blockers: {', '.join(blockers) if blockers else 'None':<25} | {cs.vEgo * 3.6:5.1f}km/h", end="")

      if last_state != state:
        if last_state is not None:
          print(f"\n[EVENT] State: {last_state} -> {state}")
          if "N/A" in state or "UNKNOWN" in state:
            if msg:
              print(f"[DIAG] msg keys: {list(msg.to_dict().keys())}")
        last_state = state

      # Button detection - show ALL buttons
      for b in cs.buttonEvents:
        if b.pressed:
          # Try to find the raw signal value if available
          print(f"\n[BUTTON] {b.type} (val: {int(b.pressed)}) | PCM: {cs.cruiseState.enabled}")


if __name__ == "__main__":
  debug_engagement()
