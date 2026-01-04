# Windows Server 2022 VM - Automatické nasazení

Toto řešení umožňuje automatické nasazení Windows Server 2022 virtuálního stroje pomocí QEMU/KVM s bezobslužnou instalací a konfigurací IIS web serveru.

## Požadavky

### Systém
- **OS**: Ubuntu 24.04 LTS (nebo novější)
- **RAM**: Minimálně 8 GB (doporučeno 12+ GB)
- **Disk**: Minimálně 80 GB volného místa
- **CPU**: Podpora virtualizace (Intel VT-x / AMD-V)
- **Virtualizace hosta**: Povoleno *Nested virtualization*

### Příprava Hostujícího stroje
```bash
sudo apt-get update
sudo apt-get install -y qemu-kvm qemu-utils libvirt-daemon-system \
    libvirt-clients bridge-utils virt-manager genisoimage python3 python3-yaml
```

### Kontrola virtualizace
```bash
# Ověření podpory KVM
egrep -c '(vmx|svm)' /proc/cpuinfo
# Výsledek > 0 znamená podporu virtualizace

# Ověření KVM modulu
lsmod | grep kvm
```

### Oprávnění
```bash
# Přidání uživatele do skupiny pro KVM
sudo usermod -aG kvm $USER
sudo usermod -aG libvirt $USER

# Odhlášení a přihlášení pro aplikování změn
# nebo použijte: newgrp kvm
```

## Struktura projektu

```
deploy/
├── deploy_vm.py           # Hlavní deployment skript
├── config.yaml            # Konfigurační soubor
├── README.md              # Tento soubor
└── deploy.md  # Detailní technický popis
web_project
├──index.html # složení závisí na webovém projektu
└──style.css
iso/
├──win_server_2022.iso # stáhnout ze stránek microsoft
└──virtio-win.iso # stáhnout 
```

## Rychlý start

### 1. Příprava ISO souborů

- Ujistěte se, že máte Windows Server 2022 ISO soubor:
```bash
ls -lh ~/iso/win_server_2022.iso
```
- Stáhněte virtio-win.iso (sada virtuálních zařízení pro windows) nutné pro bezproblémový běh KVM/QEMU
např. zde: 

https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.285-1/virtio-win.iso

### 2. Úprava konfigurace

Upravte `config.yaml` podle vašich potřeb:

```yaml
vm:
  name: "WinServer2022"
  iso_path: "~/iso/win_server_2022.iso"  # Cesta k ISO
  work_dir: "~/vm_deployments"            # Pracovní adresář
  disk_size: "60G"                        # Velikost disku
  memory: "4G"                            # RAM
  cpus: 2                                 # Počet CPU
  vnc_port: 0                             # VNC port (5900)

windows:
  computer_name: "WIN-SERVER"
  administrator_password: "Admin123!SecurePass"
  
  users:
    - username: "webadmin"
      password: "WebAdmin123!"
      group: "Administrators"
```

### 3. Příprava webového projektu (volitelné)

Pokud máte vlastní webový projekt:
```bash
mkdir -p ~/web_project
# Zkopírujte HTML, CSS, JS soubory do této složky
```

Pokud složka neexistuje, automaticky se vytvoří demo `index.html`.

### 4. Spuštění deploymentu

```bash
# Nastavení spustitelnosti
chmod +x deploy_vm.py

# Spuštění
sudo python3 deploy_vm.py config.yaml
```

### 5. Připojení k VM

**Z Windows 11 stroje:**
- Stáhněte VNC klient (např. TightVNC, RealVNC)
- Připojte se na: `<IP_Ubuntu_serveru>:5900`
- Sledujte automatickou instalaci Windows

**Poznámka:** Instalace Windows trvá cca 15-30 minut.

## Přístup k VM

### VNC přístup
```
Server: <IP_Ubuntu_serveru>
Port: 5900 (nebo 5901, podle vnc_port v config.yaml)
```

### Web server
Po dokončení instalace:
- **Z Ubuntu serveru**: http://localhost:8080
- **Z jiného stroje**: http://<IP_Ubuntu_serveru>:8080

### Přihlašovací údaje
- **Administrator**: `Admin123!SecurePass` (dle config.yaml)
- **Ostatní uživatelé**: Dle konfigurace v `config.yaml`

## Monitoring instalace

### Kontrola běžícího VM
```bash
ps aux | grep qemu
```

### Zobrazení logu
```bash
tail -f ~/vm_deployments/WinServer2022_qemu.log
```

### Přístup k log souboru uvnitř Windows
Po dokončení instalace najdete log v:
```
C:\setup_log.txt
```

## Správa VM

### Spuštění VM
```bash
~/vm_deployments/run_WinServer2022.sh
```

### Zastavení VM
Z VNC konzole:
- Přihlaste se do Windows
- Vypněte normálně přes Start menu

Nebo použijte:
```bash
pkill -f "qemu.*WinServer2022"
```

### Restart VM
Vypněte a znovu spusťte pomocí run skriptu.

### Smazání VM
```bash
rm -rf ~/vm_deployments/WinServer2022*
```

## Co se instaluje automaticky

1. **Windows Server 2022** - Základní instalace
2. **Uživatelské účty** - Dle config.yaml
3. **IIS Web Server** - Plná instalace s management konzolí
4. **Firewall pravidla** - HTTP (80) a HTTPS (443)
5. **Webový projekt** - Nasazení do `C:\inetpub\wwwroot`

## Základní příkazy

### Kontrola běžícího VM
```bash
ps aux | grep qemu
```

### Sledování logu
```bash
tail -f ~/vm_deployments/WinServer2022_qemu.log
```

### Zastavení VM
```bash
pkill -f "qemu.*WinServer2022"
```

### Restart VM (po instalaci)
```bash
# Bootuje z disku, ne z instalačního CD
~/vm_deployments/boot_WinServer2022.sh
```

### Reinstalace Windows (boot z CD)
```bash
# Spustí instalaci znovu
~/vm_deployments/run_WinServer2022.sh
```

### Kompletní reset a nový deployment
```bash
# Zastaví VM, smaže všechny soubory a vytvoří nové VM
pkill -f "qemu.*WinServer2022" 2>/dev/null; sleep 2 && rm -f ~/vm_deployments/WinServer2022* && cd /home/levap/deploy_2 && python3 deploy_vm.py config.yaml
```

## Řešení problémů

### VM se nespustí
```bash
# Kontrola KVM
sudo systemctl status libvirtd

# Kontrola oprávnění
groups | grep kvm
```

### Nefunguje VNC
```bash
# Kontrola zda běží QEMU s VNC
netstat -tulpn | grep 5900

# Kontrola firewallu
sudo ufw allow 5900
```

### Pomalá instalace
- Ujistěte se, že KVM akcelerace je aktivní
- Zvyšte RAM a CPU v config.yaml

### IIS po instalaci nefunguje
- Připojte se přes VNC
- Otevřete PowerShell jako Administrator
- Spusťte: `iisreset`
- Zkontrolujte: `Get-Service W3SVC`

## Testování

Po dokončení instalace (cca 20-30 minut):

1. **Připojení přes VNC** - Měli byste vidět přihlašovací obrazovku Windows
2. **Přihlášení** - Použijte Administrator a heslo z config.yaml
3. **Test webového serveru**:
   ```bash
   curl http://localhost:8080
   ```
4. **Otevřete prohlížeč** a přejděte na http://localhost:8080

## Další informace
- **Technická dokumentace**: viz `design.md`

## Bezpečnostní upozornění

- **Hesla v config.yaml** - V produkčním prostředí použijte silnější hesla

## Podpora

Pokud narazíte na problémy:
1. Zkontrolujte logy: `~/vm_deployments/WinServer2022_qemu.log`
2. Zkontrolujte Windows log: `C:\setup_log.txt` (uvnitř VM)
3. Ověřte konfiguraci v `config.yaml`

---
### Verze 1.0 (2025-12)
