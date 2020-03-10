#!/usr/bin/bash 

# re-pack bitstream for -12F devices and flash
echo "Converting bitstream for fe5u-12f device..."
ecppack --idcode 0x21111043 soc_basesoc_ulx3s/gateware/top.config lfe5u-12f.bit
echo "Flashing bitstream to device..."
ujprog lfe5u-12f.bit
