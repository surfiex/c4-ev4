import cereal.messaging as messaging


def debug_engagement():
  # 0.10.x uses selfdriveState for current engagement state
  services = ['carState', 'carParams', 'selfdriveState', 'can']
  sm = messaging.SubMaster(services)
  print("Starting Engagement Debugger for Kia EV4 (v2.9) [Fingerprint & Polarity Fix]...")
  print("Press Ctrl+C to stop.\n")

  last_state = None
  while True:
    sm.update(100)
    if sm.updated['carState']:
      cs = sm['carState']

      # Status logic
      status = "UNKNOWN"
      state = "UNKNOWN"

      msg = None
      if sm.updated.get('selfdriveState') or sm.alive.get('selfdriveState'):
        msg = sm['selfdriveState']

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

      # Diagnostics
      can_valid = "OK" if cs.canValid else "INVALID"
      fingerprint = cs.carFingerprint if hasattr(cs, 'carFingerprint') else "N/A"

      # Print line
      print(
        f"\r{status:<10} | {state:<12} | {raw} | FP:{fingerprint[:10]:<10} | Blockers: {', '.join(blockers) if blockers else 'None':<25} | {cs.vEgo * 3.6:5.1f}km/h",
        end="",
      )

      if last_state != state:
        if last_state is not None:
          print(f"\n[EVENT] State: {last_state} -> {state}")
        last_state = state

      # Button detection - show ALL buttons
      for b in cs.buttonEvents:
        if b.pressed:
          print(f"\n[BUTTON] {b.type} (val: {int(b.pressed)}) | PCM: {cs.cruiseState.enabled}")


if __name__ == "__main__":
  debug_engagement()
