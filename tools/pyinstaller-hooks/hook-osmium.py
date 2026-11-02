# SPDX-License-Identifier: GPL-3.0-only
from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

datas, binaries = collect_delvewheel_libs_directory('osmium')
