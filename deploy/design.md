# Technická dokumentace - Windows Server 2022 VM Deployment

## Přehled řešení

Toto řešení implementuje plně automatizované nasazení Windows Server 2022 virtuálního stroje pomocí QEMU/KVM s bezobslužnou instalací a konfigurací. Celý proces je řízen Python skriptem, který generuje potřebné konfigurační soubory a spouští virtualizační platformu.

## Architektura řešení

### Komponenty systému

```
┌─────────────────────────────────────────────────────────────┐
│                     Ubuntu 24.04 Host                       │
│                                                             │
│  ┌────────────────────────────────────────────────────┐     │
│  │            Python Deployment Script                │     │
│  │              (deploy_vm.py)                        │     │
│  └────────────────┬───────────────────────────────────┘     │
│                   │                                         │
│                   ▼                                         │
│  ┌────────────────────────────────────────────────────┐     │
│  │          Generování konfiguračních souborů         │     │
│  │  • Autounattend.xml                                │     │
│  │  • setup.ps1                                       │     │
│  │  • Web Content                                     │     │
│  └────────────────┬───────────────────────────────────┘     │
│                   │                                         │
│                   ▼                                         │
│  ┌────────────────────────────────────────────────────┐     │
│  │              QEMU/KVM Hypervisor                   │     │
│  │                                                    │     │
│  │  ┌──────────────────────────────────────────┐      │     │
│  │  │   Windows Server 2022 VM                 │      │     │
│  │  │                                          │      │     │
│  │  │  • Automatizovaná instalace              │      │     │
│  │  │  • Vytvoření uživatelských účtů          │      │     │
│  │  │  • IIS Instalace a konfigurace           │      │      │
│  │  │  • Web Project Deployment                │      │     │
│  │  └──────────────────────────────────────────┘      │     │
│  └────────────────────────────────────────────────────┘     │
│                                                             │
│  Přístupové metody k VM:                                    │
│  • VNC: Port 5900 (Remote Desktop)                          │
│  • HTTP: Port 8080 → VM:80 (Web Server)                     │
└─────────────────────────────────────────────────────────────┘
```

## Detailní popis jednotlivých kroků

### Krok 1: Inicializace a validace

**Skript**: `deploy_vm.py` - funkce `check_dependencies()`

```python
def check_dependencies(self):
    required_commands = ['qemu-system-x86_64', 'qemu-img', 'mkisofs']
```

**Co se děje:**
1. Kontrola dostupnosti potřebných příkazů v systému
2. Validace existence QEMU/KVM nástrojů
3. Kontrola nástroje `mkisofs` pro vytváření ISO

**Důvod:** Předejití selhání během deploymentu kvůli chybějícím závislostem.

### Krok 2: Vytvoření virtuálního disku

**Skript**: `deploy_vm.py` - funkce `create_disk_image()`

```bash
qemu-img create -f qcow2 <disk_path> <size>
```

**Parametry:**
- **Format**: qcow2 (QEMU Copy-On-Write)
- **Velikost**: Dle konfigurace (výchozí 60GB)
- **Vlastnosti qcow2**:
  - Dynamická alokace (nezabírá celý prostor okamžitě)
  - Podpora snapshotů
  - Komprese dat

**Příklad:**
```bash
qemu-img create -f qcow2 ~/vm_deployments/WinServer2022.qcow2 60G
```

### Krok 3: Generování Autounattend.xml

**Skript**: `deploy_vm.py` - funkce `generate_autounattend_xml()`

**Co je Autounattend.xml?**
- Windows Answer File pro bezobslužnou instalaci
- Umožňuje automatizovat celý instalační proces Windows
- Umístění: Root instalačního média (detekováno automaticky)

**Hlavní sekce:**

#### 3.1 WindowsPE Pass
```xml
<settings pass="windowsPE">
```
- **Účel**: Konfigurace před instalací
- **Nastavuje**: Jazyk, rozložení disku, výběr edice Windows

**Konfigurace disku:**
```xml
<DiskConfiguration>
  <Disk wcm:action="add">
    <CreatePartitions>
      <!-- 100MB System Reserved Partition -->
      <CreatePartition wcm:action="add">
        <Order>1</Order>
        <Size>100</Size>
        <Type>Primary</Type>
      </CreatePartition>
      <!-- Main Windows Partition -->
      <CreatePartition wcm:action="add">
        <Order>2</Order>
        <Extend>true</Extend>
        <Type>Primary</Type>
      </CreatePartition>
    </CreatePartitions>
  </Disk>
</DiskConfiguration>
```

#### 3.2 Specialize Pass
```xml
<settings pass="specialize">
```
- **Účel**: Konfigurace systému
- **Nastavuje**: Jméno počítače, síťové nastavení

#### 3.3 OOBE System Pass
```xml
<settings pass="oobeSystem">
```
- **Účel**: Konfigurace po instalaci (Out-of-Box Experience)
- **Nastavuje**: 
  - Uživatelské účty
  - Automatické přihlášení
  - První spuštěné příkazy

**Vytvoření uživatelů:**
```xml
<LocalAccounts>
  <LocalAccount wcm:action="add">
    <Password>
      <Value>heslo</Value>
      <PlainText>true</PlainText>
    </Password>
    <Name>username</Name>
    <Group>Administrators</Group>
  </LocalAccount>
</LocalAccounts>
```

**FirstLogonCommands:**
```xml
<FirstLogonCommands>
  <SynchronousCommand wcm:action="add">
    <Order>1</Order>
    <CommandLine>powershell -ExecutionPolicy Bypass -File E:\setup.ps1</CommandLine>
  </SynchronousCommand>
</FirstLogonCommands>
```
- Spustí PowerShell skript z druhého CD (E:)
- Provede post-instalační konfiguraci

### Krok 4: Generování PowerShell konfiguračního skriptu

**Skript**: `deploy_vm.py` - funkce `generate_setup_script()`

**Výstup**: `setup.ps1` - PowerShell skript pro automatickou konfiguraci

**Co skript dělá:**

#### 4.1 Instalace IIS Web Serveru
```powershell
Install-WindowsFeature -Name Web-Server -IncludeManagementTools
Install-WindowsFeature -Name Web-Mgmt-Console
```
- Instaluje IIS (Internet Information Services)
- Včetně management konzole
- Automatická konfigurace výchozího webu

#### 4.2 Konfigurace Firewallu
```powershell
New-NetFirewallRule -DisplayName "Allow HTTP" -Direction Inbound `
    -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "Allow HTTPS" -Direction Inbound `
    -Protocol TCP -LocalPort 443 -Action Allow
```
- Otevření portů 80 (HTTP) a 443 (HTTPS)
- Umožňuje externí přístup k web serveru

#### 4.3 Nasazení webového projektu
```powershell
$webRoot = "C:\inetpub\wwwroot"
Copy-Item -Path "E:\web\*" -Destination $webRoot -Recurse -Force
```
- Zkopírování souborů z CD do IIS složky
- Rekurzivní kopírování (včetně podsložek)

#### 4.4 Konfigurace uživatelů
```powershell
Add-LocalGroupMember -Group "Administrators" -Member "username"
```
- Přidání uživatelů do příslušných skupin
- Dle konfigurace v YAML

#### 4.5 Bezpečnostní optimalizace
```powershell
# Vypnutí IE Enhanced Security
Set-ItemProperty -Path $AdminKey -Name "IsInstalled" -Value 0
```
- Zjednodušení testování webu
- Pro produkci doporučeno ponechat zapnuté

#### 4.6 Logování
```powershell
Start-Transcript -Path "C:\setup_log.txt"
# ... příkazy ...
Stop-Transcript
```
- Záznam všech výstupů do logu
- Užitečné pro debugging

### Krok 5: Vytvoření konfiguračního ISO

**Skript**: `deploy_vm.py` - funkce `create_config_iso()`

**Účel**: Vytvoření druhého CD s konfiguračními soubory

**Obsah ISO:**
```
CONFIG.iso
├── Autounattend.xml    # Windows Answer File
├── setup.ps1           # PowerShell konfigurační skript
└── web/                # Webový projekt
    ├── index.html
    ├── style.css
    └── ...
```

**Příkaz:**
```bash
mkisofs -o config.iso -J -r -V "CONFIG" <source_dir>
```

**Parametry:**
- `-J`: Joliet extensions (dlouhé názvy souborů)
- `-r`: Rock Ridge (UNIX atributy)
- `-V`: Volume label

### Krok 6: Spuštění QEMU/KVM

**Skript**: `deploy_vm.py` - funkce `start_vm()`

**Generovaný příkaz:**
```bash
qemu-system-x86_64 \
    -name "WinServer2022" \
    -machine type=q35,accel=kvm \
    -cpu host \
    -smp 2 \
    -m 4G \
    -drive file=disk.qcow2,if=virtio,format=qcow2 \
    -cdrom win_server_2022.iso \
    -drive file=config.iso,media=cdrom \
    -boot order=dc \
    -vnc :0 \
    -net nic,model=virtio \
    -net user,hostfwd=tcp::8080-:80 \
    -rtc base=localtime \
    -usbdevice tablet
```



**Port Forwarding:**
- `hostfwd=tcp::8080-:80` = Host:8080 → VM:80
- Umožňuje přístup k IIS z hostu na http://localhost:8080

## Průběh instalace (Timeline)

### Fáze 1: Boot a načtení (0-2 min)
1. QEMU startuje VM
2. BIOS inicializace
3. Boot z CD (Windows ISO)
4. Windows Setup načte Autounattend.xml z druhého CD

### Fáze 2: Instalace Windows (2-15 min)
1. Windows Setup automaticky:
   - Vytvoří partitions dle Autounattend.xml
   - Naformátuje disk
   - Zkopíruje Windows soubory
   - Provede základní instalaci

### Fáze 3: Konfigurace systému (15-20 min)
1. Specialize pass:
   - Nastaví jméno počítače
   - Základní síťová konfigurace
   
2. OOBE pass:
   - Vytvoří uživatelské účty
   - Nastaví Administrator heslo
   - Nakonfiguruje automatické přihlášení

### Fáze 4: První přihlášení a konfigurace (20-30 min)
1. Windows se automaticky přihlásí jako Administrator
2. Spustí se `setup.ps1` z E: (druhé CD)
3. PowerShell skript provede:
   - Instalaci IIS (5-10 min)
   - Konfiguraci firewallu (< 1 min)
   - Nasazení webu (< 1 min)
   - Konfiguraci uživatelů (< 1 min)
   - Bezpečnostní nastavení (< 1 min)

### Fáze 5: Dokončení (30+ min)
1. Skript vypíše potvrzení
2. Systém je připraven k použití
3. IIS Web Server běží
4. Webová stránka je dostupná

## Bezpečnostní aspekty

### 1. Hesla v konfiguračním souboru
**Problém**: Hesla jsou v plain textu v YAML a Autounattend.xml

**Doporučení pro produkci:**
- Použít environment variables
- Implementovat šifrování konfigurace

```python
# Příklad s environment variables
import os
password = os.getenv('ADMIN_PASSWORD', 'default_password')
```

### 2. VNC bez autentizace
**Problém**: VNC server nemá heslo

**Řešení:**
```bash
# Přidat VNC heslo
qemu-system-x86_64 ... -vnc :0,password -monitor stdio
```

### 3. Síťová izolace
**Aktuální stav**: NAT síť s port forwardingem

**Doporučení:**
- Pro produkci použít bridge networking
- Implementovat firewall pravidla na hostu
- Omezit přístup k VNC pouze z důvěryhodných IP

### 4. Windows Updates
**Po instalaci:**
```powershell
# Povolit a spustit Windows Update
Install-Module PSWindowsUpdate
Get-WindowsUpdate
Install-WindowsUpdate -AcceptAll -AutoReboot
```

## Debugging

### Log soubory
1. **Host**: `~/vm_deployments/WinServer2022_qemu.log`
2. **Guest**: `C:\setup_log.txt`
3. **Windows Event Log**: Event Viewer → Windows Logs

### Užitečné příkazy
```bash
# Sledování QEMU logu
tail -f ~/vm_deployments/WinServer2022_qemu.log

# Kontrola VNC portu
netstat -tulpn | grep 5900

# Kontrola KVM
lsmod | grep kvm

# Připojení k QEMU monitoru
telnet localhost 4444  # s -monitor telnet:...
```

### Časté problémy

#### Windows instalace nepokračuje
- **Příčina**: Autounattend.xml nebyl načten
- **Řešení**: Zkontrolovat obsah config.iso, XML syntax

#### IIS nefunguje po instalaci
- **Příčina**: Firewall blokuje, služba nesběhla
- **Řešení**: `iisreset`, kontrola Windows Firewall

#### Pomalý výkon
- **Příčina**: KVM akcelerace není aktivní
- **Řešení**: Zkontrolovat `egrep -c '(vmx|svm)' /proc/cpuinfo`


---
### Verze 1.0 (2025-12)

