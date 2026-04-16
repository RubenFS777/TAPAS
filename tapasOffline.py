import os
import subprocess
import time
from astropy import units as u
from astropy.coordinates import Angle
from astropy.io import fits

# --- CONFIGURACIÓN ---
folder = "/home/adian/Imágenes"
# Coordenadas objetivo (Ejemplo: M81 Galaxia de Bode)
aim_to_ra = 148.888958
aim_to_dec = 69.065833

# Calibración EQ3 Bresser
turns_ra_360 = 138.25
turns_dec_360 = 89.15

def get_fits_scale(file_path):
    with fits.open(file_path) as hdul:
        header = hdul[0].header
        # 1. Focal (usualmente FOCALLEN)
        focal = float(header.get('FOCALLEN', 1400))
        # 2. Tamaño de píxel (usualmente XPIXSZ o PIXSIZE)
        pixel_size = float(header.get('XPIXSZ', 2.9))
        # 3. Binning (usualmente XBINNING)
        binning = int(header.get('XBINNING', 1))

        # Calcular la escala de placa: (Pixel_size * 206.265) / Focal
        pixel_efectivo = pixel_size * binning
        escala = (pixel_efectivo * 206.265) / focal
        return escala, focal, pixel_size, binning

def get_latest_fits(dir_path):
    # Buscamos archivos que terminen en .fit (ASIimg)
    files = [os.path.join(dir_path, f) for f in os.listdir(dir_path) if f.lower().endswith('.fit')]
    return max(files, key=os.path.getctime) if files else None

def solve_local(file_path):
    escala_real, focal, pix, bin_val = get_fits_scale(file_path)
    s_low = escala_real * 0.8
    s_high = escala_real * 1.2

    print(f"\n[1] Procesando: {os.path.basename(file_path)}")
    print(f"    Config: {focal}mm | Píxel: {pix}µm | Bin: {bin_val}x{bin_val}")
    print(f"    Escala calculada: {escala_real:.3f}\" | Rango: {s_low:.2f}-{s_high:.2f}")

    cmd = [
        "solve-field", file_path,
        "--scale-units", "arcsecperpix",
        "--scale-low", str(round(s_low, 2)),
        "--scale-high", str(round(s_high, 2)),
        "--sigma", "6", #Debe ser revaluiadao para queda caso de ruido
        "--objs", "80",
        "--downsample", "2",   # <--- AÑADE ESTO para limpiar el ruido
        "--crpix-center",
        "--overwrite"
    ]

    # Ejecutar astrometría
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # IMPORTANTE: Generar ruta al .wcs correctamente quitando .fit
    base_name = os.path.splitext(file_path)[0]
    wcs_file = base_name + ".wcs"

    if not os.path.exists(wcs_file):
        print("    [!] Error: No se pudo resolver la imagen (el archivo .wcs no existe).")
        return None

    try:
        raw_info = subprocess.check_output(["wcsinfo", wcs_file]).decode("utf-8")
        data = {}
        for line in raw_info.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                data[parts[0]] = parts[1]
        
        data['log_output'] = result.stdout
        return data
    except Exception as e:
        print(f"    [!] Error al leer wcsinfo: {e}")
        return None

def get_objects(res_data):
    log = res_data.get('log_output', "")
    if "Your field contains:" not in log:
        return "No se detectaron objetos notables específicos."

    parts = log.split("Your field contains:")
    useful_text = parts[1].split("Deleting")[0]
    
    found = []
    for line in useful_text.splitlines():
        clean = line.strip().replace("- ", "")
        if clean and "Checking" not in clean and "done" not in clean:
            found.append(clean)
    
    return " | ".join(found) if found else "No se detectaron objetos notables específicos."

# --- PROCESO PRINCIPAL ---
target_file = get_latest_fits(folder)

if target_file:
    res = solve_local(target_file)
    
    if res:
        # 1. Posición actual
        ra_actual = float(res['ra_center'])
        dec_actual = float(res['dec_center'])
        print(f"\nESTÁS APUNTANDO A:")
        print(f"    RA:  {res['ra_center_hms']} ({ra_actual:.4f}°)")
        print(f"    DEC: {res['dec_center_dms']} ({dec_actual:.4f}°)")

        # 2. Objetos notables
        print(f"    CAMPO: {get_objects(res)}")

        # 3. Diferencia al objetivo
        diff_ra = ra_actual - aim_to_ra
        diff_dec = dec_actual - aim_to_dec
        print(f"\nDESVIACIÓN:")
        print(f"    ΔRA: {diff_ra:.4f}° | ΔDEC: {diff_dec:.4f}°")

        # 4. Acción en mandos finos EQ3
        vueltas_ra = (diff_ra / 360) * turns_ra_360
        vueltas_dec = (diff_dec / 360) * turns_dec_360

        print("\n[ AJUSTE MANUAL EQ3 ]")
        sentido_ra = "DERECHA (Oeste)" if vueltas_ra > 0 else "IZQUIERDA (Este)"
        sentido_dec = "ANTIHORARIO" if vueltas_dec > 0 else "HORARIO"

        print(f"    Mando RA:  {abs(vueltas_ra):.3f} vueltas hacia la {sentido_ra}")
        print(f"    Mando DEC: {abs(vueltas_dec):.3f} vueltas sentido {sentido_dec}")
    else:
        print("\n[!] Fallo en el análisis. Prueba con otra foto.")
else:
    print("\n[!] No se encontró ningún archivo .fit en la carpeta.")
