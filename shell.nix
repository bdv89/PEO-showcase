# Compat pour `nix-shell` (sans flakes). Équivalent du devShell du flake.nix.
{ pkgs ? import <nixpkgs> { } }:

let
  pyEnv = pkgs.python3.withPackages (ps: with ps; [
    pyvisa
    pyvisa-py
    pyusb       # transport USBTMC (pyvisa-py) -- nécessite libusb1, ajouté ci-dessous
    psutil
    zeroconf
    numpy
    h5py
    scipy
    matplotlib
    pandas
    pyqtgraph
    pyqt5
    pytest
  ]);
  # python3Packages.pyqt5 n'embarque pas les plugins de plateforme Qt
  # (xcb/wayland/offscreen) : sans ça, "qt.qpa.plugin: Could not find the Qt
  # platform plugin". Ils vivent dans la sortie "bin" de qtbase, ici prise
  # depuis le MÊME nixpkgs que pyqt5 (évite un décalage ABI).
  qtPlatformPlugins = "${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins/platforms";
in
pkgs.mkShell {
  # libusb1 : pyusb le trouve via ctypes.util.find_library ; nécessaire pour le
  # transport USBTMC (scope branché en USB, cf. --usb / docs/architecture.md).
  packages = [ pyEnv pkgs.libusb1 ];
  shellHook = ''
    export QT_QPA_PLATFORM_PLUGIN_PATH="${qtPlatformPlugins}"
    echo "Env scope prêt : python -m scope.cli idn <ip>  |  pytest"
  '';
}
