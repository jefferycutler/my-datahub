#!/bin/bash
###########################################################
# Test Kafka VM reset script
# Shutdown and restore test kafka hosts to pre kafka state
# Optionally restart them in headless mode
##########################################################

# --- Configuration ---------------------------------------
VMS=(tkf01 tkf02 tkf03)
SNAPSHOT="pre-kafka-2drive"
# ---------------------------------------------------------

# Ask once, up front
read -r -p "Restart the VMs in headless mode after restore? [y/N] " answer
case "$answer" in
  [Yy]|[Yy][Ee][Ss]) restart=1 ;;
  *)                 restart=0 ;;
esac

for vm in "${VMS[@]}"; do
  echo "Shutting Down $vm..."
  VBoxManage controlvm "$vm" acpipowerbutton
  # Loop until the VM state is "poweroff"
  while [ "$(VBoxManage showvminfo "$vm" --machinereadable | grep -c 'VMState="poweroff"')" -eq 0 ]; do
    echo -n "."
    sleep 2
  done
  echo
  echo "Restoring $vm to snapshot '$SNAPSHOT'..."
  VBoxManage snapshot "$vm" restore "$SNAPSHOT"
done

if [ "$restart" -eq 1 ]; then
  for vm in "${VMS[@]}"; do
    echo "Starting $vm in headless mode..."
    VBoxManage startvm "$vm" --type headless
  done
fi