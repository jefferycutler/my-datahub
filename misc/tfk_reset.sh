#!/bin/bash
###########################################################
# Test Kafka VM reset script
# Shutdown and restore test kafka hosts to pre kafka state
##########################################################
for vm in tkf01 tkf02 tkf03; do
  echo "Shutting Down  $vm..."
  VBoxManage controlvm "$vm" acpipowerbutton
  # Loop until the VM state is "poweroff"
  while [ "$(VBoxManage showvminfo "$vm" --machinereadable | grep -c 'VMState="poweroff"')" -eq 0 ]; do
    echo -n "."
    sleep 2
  done
  echo "Restoring to Pre Kafka state..."
  VBoxManage snapshot "$vm" restore "pre-kafka.v3"
done
