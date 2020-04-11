#!/usr/bin/env python3

# Based on litex boards/targets/ulx3s.py
# This file instantiates an externally attached SPI Flash so we can read & write its data

# This file is Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2018 David Shah <dave@ds0.me>
# This file is Copyright (c) 2020 John Kelley <john@kelley.ca>
# License: BSD

LX_DEPENDENCIES = ["riscv", "nextpnr-ecp5", "yosys"]

# Import lxbuildenv to integrate the deps/ directory
import lxbuildenv

import argparse
import sys

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.io import DDROutput

# use our local ulx3s platform
import ulx3s

from litex.build.lattice.trellis import trellis_args, trellis_argdict

from litex.soc.cores import spi_flash
from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *

from litedram import modules as litedram_modules
from litedram.phy import GENSDRPHY

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.clock_domains.cd_sys    = ClockDomain()
        self.clock_domains.cd_sys_ps = ClockDomain(reset_less=True)
        self.clock_domains.cd_usb_12 = ClockDomain()
        self.clock_domains.cd_usb_48 = ClockDomain()

        # # #

        # Clk / Rst
        clk25 = platform.request("clk25")
        rst   = platform.request("rst")
        platform.add_period_constraint(clk25, 1e9/25e6)

        # PLL
        self.submodules.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(rst)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys,    sys_clk_freq, margin=0)
        pll.create_clkout(self.cd_sys_ps, sys_clk_freq, margin=0, phase=90)
        pll.create_clkout(self.cd_usb_12, 12e6,         margin=0)

        self.comb += self.cd_usb_48.clk.eq(self.cd_sys.clk)

        self.specials += AsyncResetSynchronizer(self.cd_sys, ~pll.locked | rst)

        # SDRAM clock
        #self.comb += platform.request("sdram_clock").eq(self.cd_sys_ps.clk)
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), ClockSignal("sys_ps"))

        # Prevent ESP32 from resetting FPGA
        self.comb += platform.request("wifi_gpio0").eq(1)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    SPIFLASH_PAGE_SIZE    = 256
    SPIFLASH_SECTOR_SIZE  = 64*1024
    # The dummy cycles comes from section 8.1.3 "Instruction Set Table 2" of the W25Q64FW datasheet
    # which states that FastRead command has one dummy byte. This value should be the same for Quad
    # output (spiflash4x) for this IC.
    SPIFLASH_DUMMY_CYCLES = 8
    def __init__(self, device="LFE5U-45F", toolchain="trellis",
        sys_clk_freq=int(48e6), sdram_module_cls="MT48LC16M16", **kwargs):

        platform = ulx3s.Platform(device=device, toolchain=toolchain)

        # fix for with_uart being defined more than once
        kwargs["with_uart"] = False
        # SoCSDRAM ---------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, clk_freq=sys_clk_freq, **kwargs)

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # SPI FLASH
        spi_pads = platform.request("spiflash")
	# add constants so the BIOS knows to enable spiflash commands
        self.add_constant("SPIFLASH_PAGE_SIZE", self.SPIFLASH_PAGE_SIZE)
        self.add_constant("SPIFLASH_SECTOR_SIZE", self.SPIFLASH_SECTOR_SIZE)
        self.submodules.spiflash = spi_flash.SpiFlash(spi_pads, dummy=self.SPIFLASH_DUMMY_CYCLES, endianness="little")
        self.register_mem("spiflash", 0x20000000, self.spiflash.bus, size=16 * 1024 * 1024)
        self.add_csr("spiflash")

        import valentyusb.usbcore.io as usbio
        import valentyusb.usbcore.cpu.cdc_eptri as cdc_eptri
        usb_pads = self.platform.request("usb")
        usb_iobuf = usbio.IoBuf(usb_pads.d_p, usb_pads.d_n, usb_pads.pullup)
        self.submodules.uart = cdc_eptri.CDCUsb(usb_iobuf, vid=0x1209, pid=0x5835, product="ulx3s CDC", manufacturer="hedge")
        self.add_csr('uart')
        self.add_interrupt('uart')

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.submodules.sdrphy = GENSDRPHY(platform.request("sdram"))
            self.add_sdram("sdram",
                phy = self.sdrphy,
                module = getattr(litedram_modules, sdram_module_cls)(sys_clk_freq, "1:1"),
                origin = self.mem_map["main_ram"],
                size = kwargs.get("max_sdram_size", 0x40000000),
                l2_cache_size = kwargs.get("l2_size", 8192),
                l2_cache_min_data_width = kwargs.get("min_l2_data_width", 128),
                l2_cache_reverse = True
            )
            #self.register_sdram(self.sdrphy,
            #                    sdram_module.geom_settings,
            #                    sdram_module.timing_settings)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on ULX3S")
    parser.add_argument("--gateware-toolchain", dest="toolchain", default="trellis",
        help="gateware toolchain to use, trellis (default) or diamond")
    parser.add_argument("--device", dest="device", default="LFE5U-25F",
        help="FPGA device, ULX3S can be populated with LFE5U-45F (default) or LFE5U-85F")
    parser.add_argument("--sys-clk-freq", default=48e6,
                        help="system clock frequency (default=50MHz)")
    parser.add_argument("--sdram-module", default="MT48LC16M16",
                        help="SDRAM module: MT48LC16M16, AS4C32M16 or AS4C16M16 (default=MT48LC16M16)")
    parser.add_argument("--nextpnr-seed", default=0, help="Select nextpnr pseudo random seed")
    parser.add_argument("--nextpnr-placer", default="heap", choices=["sa", "heap"], help="Select nextpnr placer algorithm")
    builder_args(parser)
    soc_sdram_args(parser)
    trellis_args(parser)
    args = parser.parse_args()
   
    soc = BaseSoC(device=args.device, toolchain=args.toolchain,
        sdram_module_cls=args.sdram_module,
        sys_clk_freq=int(float(args.sys_clk_freq)),
        **soc_sdram_argdict(args))

    builder = Builder(soc, **builder_argdict(args))
    builder_kargs = trellis_argdict(args) if args.toolchain == "trellis" else {}
    builder.build(**builder_kargs)

if __name__ == "__main__":
    main()
