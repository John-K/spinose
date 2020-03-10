# SPINose
SPINose is a quick and dirty gateware for ULX3S to enable dumping  external SPI NOR flash via litex's builtin `mr`  command.

## Requirements

You must have `nextpnr-ecp5`, `yosys`, and `riscv64-unknown-elf-gcc` available in your `$PATH`

SPINose uses `lxbuildenv.py` to manage litex and migen.

## Building
To build the firmware and gateware, simply invoke the main python script:

`./spinose.py`

This will produce `soc_basesoc_ulx3s/gateware/top.bit` suitable for LFE5U-25F devices, if your ULX3S has a LFE5U-12F device, you can convert and flash this bitstream by invoking the included `flash-12f.sh` script. If you have an LFE5U-45F or -85F device, you must pass this using the `--device` argument to `./spinose.py`

## Example Usage
Via the litex BIOS console, dumping a 16MiB SPI Nor is as simple as:

`mr 0x20000000 16777216`

and capturing the output to a file. I do this by redirecting the output of my terminal emulator to a file using tee

`miniterm.py --raw /dev/ttyS1 115200 | tee spinor.dump`

You can then edit the dump to only contain lines starting with `0x2XXXXXXX` addresses and convert your dump to a binary file using `colrm` and `xxd`:

`colrm 1 12 < spinor.dump | colrm 48 70 | xxd -r -p > spinor.bin`

The size of the resulting file should be exactly the same as the parameter to the `mr` command, if it is not then you either have an incomplete dump or you had stray information in your dump file when invoking `xxd`

You can also calculate the CRC32 of the data via the litex BIOS console with `crc 0x20000000 16777216` and then compare
 it against the CRC32 of your spinor.bin file.
 
## Future work
* [ ] implement a more efficient data transfer method
* [ ] figure out how to augment litex's `platform/ulx3s.py` `_io` definitions from `spinose.py` instead of maintaining a local copy
* [ ] make use of QUAD SPI mode via `spiflash4x`
* [ ] support more than one spiflash IC
