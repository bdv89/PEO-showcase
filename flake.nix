{
  description = "Pilotage SCPI du Siglent SDS1204X-E (PyVISA / pyvisa-py, multiplateforme)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
      pyEnv = pkgs: pkgs.python3.withPackages (ps: with ps; [
        pyvisa
        pyvisa-py   # backend Python pur : pas de NI-VISA
        pyusb       # transport USBTMC (scope branché en USB) -- nécessite libusb1
        psutil      # requis par pyvisa-py
        zeroconf    # découverte VXI-11 (optionnel mais recommandé)
        numpy
        h5py        # export waveform HDF5
        scipy       # export waveform MAT
        matplotlib  # plots statiques
        pandas      # extraction des plateaux (synthèse de fin de série)
        pyqtgraph   # affichage live
        pyqt5       # backend Qt pour pyqtgraph
        pytest
      ]);
    in
    {
      devShells = forAll (system:
        let
          pkgs = pkgsFor system;
          # python3Packages.pyqt5 n'embarque pas les plugins de plateforme Qt
          # (xcb/wayland/offscreen) : sans ça, "qt.qpa.plugin: Could not find
          # the Qt platform plugin". Ils vivent dans la sortie "bin" de qtbase,
          # ici prise depuis le MÊME nixpkgs que pyqt5 (évite un décalage ABI).
          qtPlatformPlugins = "${pkgs.qt5.qtbase.bin}/lib/qt-${pkgs.qt5.qtbase.version}/plugins/platforms";
        in {
          default = pkgs.mkShell {
            # libusb1 : pyusb le trouve via ctypes.util.find_library (transport USBTMC).
            packages = [ (pyEnv pkgs) pkgs.libusb1 ];
            shellHook = ''
              export QT_QPA_PLATFORM_PLUGIN_PATH="${qtPlatformPlugins}"
              echo "Env scope prêt : python -m scope.cli idn <ip>  |  pytest"
            '';
          };
        });
    };
}
