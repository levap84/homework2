#!/usr/bin/env python3
"""
Windows Server VM Deployment Script
Automaticky nasadí Windows Server VM pomocí QEMU/KVM s bezobslužnou konfigurací

Popis:
    Tento skript automatizuje celý proces nasazení Windows Server 2022 VM:
    - Načte konfiguraci z YAML souboru
    - Vytvoří virtuální disk pro VM
    - Vygeneruje Autounattend.xml pro bezobslužnou instalaci Windows
    - Vytvoří PowerShell setup skript pro post-instalační konfiguraci
    - Připraví ISO soubory s konfiguračními daty
    - Spustí VM pomocí QEMU s připojenými médii
"""

# === IMPORTY ===

# yaml - pro načítání YAML konfiguračních souborů (config.yaml)
import yaml

# os - pro práci s operačním systémem (cesty, kontrola existence souborů)
import os

# sys - pro systémové funkce (exit, argumenty příkazové řádky)
import sys

# subprocess - pro spouštění externích příkazů (qemu-img, mkisofs, mount, atd.)
import subprocess

# shutil - pro práci se soubory a složkami (kopírování, mazání, hledání příkazů)
import shutil

# tempfile - pro vytváření dočasných složek a souborů
import tempfile

# xml.etree.ElementTree - pro práci s XML (v tomto projektu nepoužíváme, ale je připraveno)
import xml.etree.ElementTree as ET

# pathlib.Path - moderní objektově orientovaný způsob práce s cestami k souborům
from pathlib import Path

# time - pro časové operace (sleep, měření času) - v tomto projektu nepoužíváme
import time

# argparse - pro parsování argumentů příkazové řádky (config.yaml cesta)
import argparse

class WindowsVMDeployer:
    """
    Hlavní třída pro deployment Windows Server VM.
    
    Tato třída zapouzdřuje všechny kroky potřebné pro nasazení VM:
    - Kontrolu závislostí
    - Vytvoření virtuálního disku
    - Generování konfiguračních souborů
    - Spuštění VM pomocí QEMU
    
    Attributes:
        config (dict): Načtená konfigurace z YAML souboru
        vm_name (str): Název virtuálního stroje (z config['vm']['name'])
        work_dir (Path): Pracovní adresář pro soubory VM (disk, ISO, logy)
    """
    
    def __init__(self, config_file):
        """
        Inicializace deployeru s konfiguračním souborem.
        
        Args:
            config_file (str): Cesta k YAML konfiguračnímu souboru
            
        Raises:
            FileNotFoundError: Pokud config_file neexistuje
            yaml.YAMLError: Pokud je YAML soubor nevalidní
        """
        # Otevření a načtení YAML konfiguračního souboru
        with open(config_file, 'r', encoding='utf-8') as f:
            # yaml.safe_load() načte YAML do Python slovníku
            self.config = yaml.safe_load(f)
        
        # Uložení názvu VM pro pozdější použití (např. v názvech souborů)
        self.vm_name = self.config['vm']['name']
        
        # Pracovní adresář pro všechny soubory VM
        self.work_dir = Path(self.config['vm']['work_dir']).expanduser()
        
        # Vytvoření pracovního adresáře, pokud neexistuje
        # parents=True vytvoří i rodičovské složky
        # exist_ok=True nehlásí chybu, pokud již existuje
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
    def check_dependencies(self):
        """
        Kontrola dostupnosti potřebných systémových příkazů.
        
        Zkontroluje, zda jsou v systému dostupné všechny potřebné nástroje:
        - qemu-system-x86_64: Hlavní QEMU emulátor
        - qemu-img: Nástroj pro práci s virtuálními disky 
        - mkisofs: Nástroj pro vytváření ISO souborů
        
        Raises:
            SystemExit: Pokud některá závislost chybí (exit code 1)
        """
        print("Kontrola závislostí...")
        
        # Seznam povinných příkazů, které musí být dostupné v PATH
        required_commands = ['qemu-system-x86_64', 'qemu-img', 'mkisofs']
        missing = []
        
        # Projít všechny povinné příkazy a zjistit, které chybí
        for cmd in required_commands:
            # shutil.which() hledá příkaz v PATH
            # Vrací cestu k příkazu, nebo None pokud nenalezen
            if not shutil.which(cmd):
                missing.append(cmd)
        
        # Pokud nějaký příkaz chybí, vypsat chybu a ukončit program
        if missing:
            print(f"CHYBA: Chybějící závislosti: {', '.join(missing)}")
            print("Nainstalujte: sudo apt-get install qemu-kvm qemu-utils genisoimage")
            sys.exit(1)  # Ukončení s chybovým kódem 1
        
        print("Všechny závislosti jsou dostupné")
    
    def create_disk_image(self):
        """
        Vytvoření virtuálního disku pro VM.
        
        Vytvoří QCOW2 virtuální disk, pokud ještě neexistuje.
        
        Returns:
            Path: Cesta k vytvořenému virtuálnímu disku
            
        Raises:
            subprocess.CalledProcessError: Pokud selže vytvoření disku
        """
        # Sestavení cesty k virtuálnímu disku
        # Formát: ~/vm_deployments/WinServer2022.qcow2
        disk_path = self.work_dir / f"{self.vm_name}.qcow2"
        
        # Načtení požadované velikosti disku z konfigurace
        disk_size = self.config['vm']['disk_size']
        
        # Pokud disk již existuje, použít ho (např. při restartu deploymentu)
        if disk_path.exists():
            print(f"Disk {disk_path} již existuje, používám existující")
            return disk_path
        
        print(f"Vytvářím virtuální disk {disk_size}...")
        
        # Sestavení příkazu pro vytvoření disku pomocí qemu-img
        cmd = [
            'qemu-img', 'create',  # Příkaz pro vytvoření obrazu
            '-f', 'qcow2',         # Format: QCOW2
            str(disk_path),        # Cesta k výstupnímu souboru
            disk_size              # Velikost
        ]
        
        # Spuštění příkazu
        # check=True způsobí vyvolání výjimky, pokud příkaz selže
        subprocess.run(cmd, check=True)
        
        print(f"Disk vytvořen: {disk_path}")
        return disk_path
    
    def generate_autounattend_xml(self):
        """
        Generování Autounattend.xml souboru pro bezobslužnou instalaci Windows.
        
        Obsahuje:
        - Nastavení jazyka a regionu
        - Konfiguraci disků (partitioning)
        - Výběr edice Windows k instalaci
        - Uživatelské účty a hesla
        - Příkazy ke spuštění po instalaci
        - Cesty k ovladačům (virtio drivers)
        
        Instalace probíhá ve 3 fázích:
        1. windowsPE - Před instalací (jazyk, disky, ovladače)
        2. specialize - Během instalace (jméno počítače, síť)
        3. oobeSystem - Po instalaci (uživatelé, autologin, skripty)
        
        Returns:
            str: Kompletní XML obsah Autounattend.xml souboru
        """
        print("Generuji Autounattend.xml...")
        
        # Mapování krátkých názvů edic na přesné názvy obrazů v install.wim souboru
        # Tyto názvy musí přesně odpovídat názvům v Windows ISO
        # (lze zjistit pomocí: dism /Get-WimInfo /WimFile:install.wim)
        edition_mapping = {
            'standard': 'Windows Server 2022 SERVERSTANDARD',           # S GUI
            'core': 'Windows Server 2022 SERVERSTANDARDCORE',           # Bez GUI
            'datacenter': 'Windows Server 2022 SERVERDATACENTER',       # Datacenter s GUI
            'datacenter-core': 'Windows Server 2022 SERVERDATACENTERCORE'  # Datacenter bez GUI
        }
        
        # Načtení vybrané edice z konfigurace, výchozí je 'standard'
        windows_edition = self.config['windows'].get('windows_edition', 'standard')
        
        # Převod krátké názvu na úplný název obrazu
        image_name = edition_mapping.get(windows_edition, 'Windows Server 2022 SERVERSTANDARD')
        
        print(f"  Vybraná edice: {image_name}")
        
        # === Generování XML sekce s uživatelskými účty ===
        # Načtení seznamu uživatelů z konfigurace
        users_xml = ""
        
        # Iterace přes všechny uživatele definované v config.yaml
        for user in self.config['windows']['users']:
            # Pro každého uživatele vygenerovat LocalAccount XML element
            users_xml += f"""
            <LocalAccount wcm:action="add">
                <Password>
                    <Value>{user['password']}</Value>
                    <PlainText>true</PlainText>  <!-- Heslo v plain textu (pro automatizaci) -->
                </Password>
                <Description>{user.get('description', '')}</Description>  <!-- Popis účtu -->
                <DisplayName>{user['username']}</DisplayName>  <!-- Zobrazované jméno -->
                <Group>{user.get('group', 'Users')}</Group>  <!-- Skupina (Users/Administrators) -->
                <Name>{user['username']}</Name>  <!-- Přihlašovací jméno -->
            </LocalAccount>"""
        
        # Načtení hesla pro vestavěný Administrator účet
        # get() použije výchozí hodnotu, pokud není v config.yaml specifikováno
        administrator_password = self.config['windows'].get('administrator_password', 'Admin123!')
        
        # Načtení jména počítače (hostname), které se zobrazí ve Windows
        computer_name = self.config['windows'].get('computer_name', 'WIN-SERVER')
        
        # === SESTAVENÍ KOMPLETNÍHO AUTOUNATTEND.XML SOUBORU ===
        # Tento XML soubor řídí celou bezobslužnou instalaci Windows
        xml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    
    <!-- ============================================================ -->
    <!-- PASS 1: windowsPE - Instalace Windows (před instalací OS) -->
    <!-- ============================================================ -->
    <settings pass="windowsPE">
        
        <!-- Nastavení jazyka a regionu -->
        <component name="Microsoft-Windows-International-Core-WinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <SetupUILanguage>
                <UILanguage>en-US</UILanguage>  <!-- Jazyk instalačního rozhraní -->
            </SetupUILanguage>
            <InputLocale>en-US</InputLocale>     <!-- Rozložení klávesnice -->
            <SystemLocale>en-US</SystemLocale>   <!-- Systémový jazyk -->
            <UILanguage>en-US</UILanguage>       <!-- Jazyk uživatelského rozhraní -->
            <UserLocale>en-US</UserLocale>       <!-- Formát data, času, měny -->
        </component>
        
        <!-- Automatické načtení VirtIO ovladačů během instalace -->
        <!-- Bez těchto ovladačů by Windows neviděl virtio disk a síťovou kartu -->
        <component name="Microsoft-Windows-PnpCustomizationsWinPE" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <DriverPaths>
                <!-- Ovladač pro virtio storage (disk) - Windows musí vidět virtuální disk -->
                <PathAndCredentials wcm:action="add" wcm:keyValue="1">
                    <Path>D:\\viostor\\2k22\\amd64</Path>  <!-- D: = virtio-win.iso -->
                </PathAndCredentials>
                <!-- Ovladač pro virtio network (síť) - pro síťovou komunikaci -->
                <PathAndCredentials wcm:action="add" wcm:keyValue="2">
                    <Path>D:\\NetKVM\\2k22\\amd64</Path>
                </PathAndCredentials>
            </DriverPaths>
        </component>
        
        <!-- Hlavní instalace Windows - disk konfigurace a výběr edice -->
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            
            <!-- Konfigurace disku - vytvoření a formátování partitionů -->
            <DiskConfiguration>
                <Disk wcm:action="add">
                    <DiskID>0</DiskID>                    <!-- První disk (virtuální disk VM) -->
                    <WillWipeDisk>true</WillWipeDisk>     <!-- Smazat všechna stávající data -->
                    <CreatePartitions>
                        <!-- Vytvoření jedné velké partition pro Windows -->
                        <CreatePartition wcm:action="add">
                            <Order>1</Order>              <!-- První (a jediná) partition -->
                            <Type>Primary</Type>          <!-- Primární partition (bootovací) -->
                            <Extend>true</Extend>         <!-- Použít celou dostupnou kapacitu -->
                        </CreatePartition>
                    </CreatePartitions>
                    <ModifyPartitions>
                        <!-- Formátování a označení partition -->
                        <ModifyPartition wcm:action="add">
                            <Active>true</Active>          <!-- Nastavení jako aktivní (bootovací) -->
                            <Format>NTFS</Format>          <!-- Souborový systém NTFS -->
                            <Label>Windows</Label>         <!-- Název svazku -->
                            <Order>1</Order>
                            <PartitionID>1</PartitionID>
                        </ModifyPartition>
                    </ModifyPartitions>
                </Disk>
            </DiskConfiguration>
            
            <!-- Výběr edice Windows k instalaci -->
            <ImageInstall>
                <OSImage>
                    <InstallFrom>
                        <!-- Specifikace přesného názvu obrazu z install.wim -->
                        <MetaData wcm:action="add">
                            <Key>/IMAGE/NAME</Key>
                            <Value>{image_name}</Value>  <!-- Např. "Windows Server 2022 SERVERSTANDARD" -->
                        </MetaData>
                    </InstallFrom>
                    <InstallTo>
                        <DiskID>0</DiskID>              <!-- Instalovat na disk 0 -->
                        <PartitionID>1</PartitionID>    <!-- Na partition 1 -->
                    </InstallTo>
                </OSImage>
            </ImageInstall>
            
            <!-- Základní uživatelské údaje pro instalaci -->
            <UserData>
                <AcceptEula>true</AcceptEula>      <!-- Automatické přijetí licenčních podmínek -->
                <FullName>Administrator</FullName>  <!-- Celé jméno uživatele -->
                <Organization>Organization</Organization>  <!-- Název organizace -->
            </UserData>
        </component>
    </settings>
    
    <!-- ============================================================ -->
    <!-- PASS 2: specialize - Konfigurace systému (během instalace) -->
    <!-- ============================================================ -->
    <settings pass="specialize">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <!-- Nastavení jména počítače (hostname) -->
            <ComputerName>{computer_name}</ComputerName>
        </component>
    </settings>
    
    <!-- ============================================================ -->
    <!-- PASS 3: oobeSystem - Po instalaci (OOBE = Out-Of-Box Experience) -->
    <!-- ============================================================ -->
    <settings pass="oobeSystem">
        <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            
            <!-- Automatické přihlášení Administratorů po instalaci -->
            <!-- Umožní spustit setup skripty bez manuálního přihlášení -->
            <AutoLogon>
                <Password>
                    <Value>{administrator_password}</Value>
                    <PlainText>true</PlainText>
                </Password>
                <Enabled>true</Enabled>                <!-- Povolit automatické přihlášení -->
                <Username>Administrator</Username>     <!-- Přihlásit jako Administrator -->
            </AutoLogon>
            
            <!-- Nastavení OOBE (původní konfigurace Windows) -->
            <!-- Skrytí všech dialogů pro plně automatickou instalaci -->
            <OOBE>
                <HideEULAPage>true</HideEULAPage>                      <!-- Skrýt licenční podmínky -->
                <HideLocalAccountScreen>true</HideLocalAccountScreen>  <!-- Skrýt vytváření účtu -->
                <HideOnlineAccountScreens>true</HideOnlineAccountScreens>  <!-- Bez Microsoft účtu -->
                <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>  <!-- Bez WiFi nastavení -->
                <ProtectYourPC>3</ProtectYourPC>  <!-- Zakázat Windows Defender (3=disable) -->
            </OOBE>
            
            <!-- Konfigurace uživatelských účtů -->
            <UserAccounts>
                <!-- Heslo pro vestavěný Administrator účet -->
                <AdministratorPassword>
                    <Value>{administrator_password}</Value>
                    <PlainText>true</PlainText>
                </AdministratorPassword>
                <!-- Přidání lokálních uživatelských účtů z konfigurace -->
                <LocalAccounts>{users_xml}
                </LocalAccounts>
            </UserAccounts>
            
            <!-- Příkazy ke spuštění při prvním přihlášení -->
            <!-- Tyto příkazy se spustí AUTOMATICKY po prvním bootu Windows -->
            <FirstLogonCommands>
                <SynchronousCommand wcm:action="add">
                    <Order>1</Order>  <!-- Pořadí spuštění (může být více příkazů) -->
                    <!-- Spuštění PowerShell setup skriptu z config ISO (F:) -->
                    <!-- ExecutionPolicy Bypass povolí spuštění nepodepsaných skriptů -->
                    <CommandLine>powershell -ExecutionPolicy Bypass -File F:\\setup.ps1</CommandLine>
                    <Description>Run setup script</Description>
                </SynchronousCommand>
            </FirstLogonCommands>
        </component>
    </settings>
</unattend>"""
        
        return xml_content
    
    def generate_setup_script(self):
        """
        Generování PowerShell skriptu pro post-instalační konfiguraci.
        
        Tento skript se automaticky spustí při prvním přihlášení do Windows
        (prostřednictvím FirstLogonCommands v Autounattend.xml).
        
        Skript provede:
        1. Instalaci IIS Web Serveru
        2. Konfiguraci firewallu (otevření portů 80, 443)
        3. Zkopírování webového projektu do IIS (C:\inetpub\wwwroot)
        4. Přidání uživatelů do příslušných skupin
        5. Vypnutí IE Enhanced Security Configuration
        6. Restart IIS
        
        Všechny akce jsou logovovány do C:\setup_log.txt pro ladění.
        
        Returns:
            str: Kompletní PowerShell skript jako string
        """
        print("Generuji setup.ps1...")
        
        # Načtení cesty ke zdrojovému webovému projektu z konfigurace
        web_source = self.config['windows']['web_project']['source_folder']
        
        # === SESTAVENÍ POWERSHELL SETUP SKRIPTU ===
        script_content = f"""# Windows Server Setup Script
# Tento skript se spustí automaticky po instalaci Windows
# (voláno z Autounattend.xml -> FirstLogonCommands)

# Začátek logování - všechny výstupy se uloží do C:\\setup_log.txt
# Transcript zachytí všechny Write-Host výstupy a chyby
Start-Transcript -Path "C:\\setup_log.txt"

Write-Host "Začínám konfiguraci Windows Serveru..."

# === INSTALACE IIS WEB SERVERU ===
Write-Host "Instaluji IIS Web Server..."
# Install-WindowsFeature - PowerShell cmdlet pro instalaci Windows funkcí/rolí
# Web-Server = IIS (Internet Information Services)
# IncludeManagementTools = přidá i grafické nástroje pro správu
Install-WindowsFeature -Name Web-Server -IncludeManagementTools

# Web-Mgmt-Console = IIS Manager (grafická konzole pro správu IIS)
Install-WindowsFeature -Name Web-Mgmt-Console

# === KONFIGURACE FIREWALLU ===
Write-Host "Konfiguruji firewall..."
# Otevření portů pro HTTP a HTTPS komunikaci
# Bez těchto pravidel by web server nebyl přístupný zvenku
New-NetFirewallRule -DisplayName "Allow HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
New-NetFirewallRule -DisplayName "Allow HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
"""

        # Přidání RDP konfigurace, pokud je povolena
        rdp_config = self.config['vm'].get('rdp', {})
        if rdp_config.get('enabled', False):
            script_content += """
# === KONFIGURACE REMOTE DESKTOP (RDP) ===
Write-Host "Konfiguruji Remote Desktop..."

# Povolení Remote Desktop
Set-ItemProperty -Path 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server' -Name "fDenyTSConnections" -Value 0

# Povolení Remote Desktop přes firewall
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

# Nebo explicitní vytvoření pravidla (pokud neexistuje)
New-NetFirewallRule -DisplayName "Allow RDP" -Direction Inbound -Protocol TCP -LocalPort 3389 -Action Allow -ErrorAction SilentlyContinue

Write-Host "Remote Desktop povolen na portu 3389"
"""

        script_content += """
# === NASAZENÍ WEBOVÉHO PROJEKTU ===
Write-Host "Nastavuji webový projekt..."
# Výchozí webová složka IIS
$webRoot = "C:\\inetpub\\wwwroot"

# Zkopírování souborů z CD (F:\\web\\*)
# F: = config ISO připojené jako třetí CD-ROM
if (Test-Path "F:\\web") {{
    Write-Host "Kopíruji webové soubory..."
    # Copy-Item rekurzivně zkopíruje všechny soubory a složky
    # -Force přepíše existující soubory
    Copy-Item -Path "F:\\web\\*" -Destination $webRoot -Recurse -Force
}}

# === RESTART IIS ===
Write-Host "Restartuji IIS..."
# iisreset - příkaz pro restart IIS (aplikuje změny)
iisreset

# === KONFIGURACE UŽIVATELŮ ===
Write-Host "Konfiguruji uživatele..."
"""

        # Přidání konfigurace pro každého uživatele
        for user in self.config['windows']['users']:
            # Pouze uživatelé, kteří mají být v Administrators skupině
            if user.get('group', 'Users') == 'Administrators':
                script_content += f"""
# Přidání {user['username']} do skupiny Administrators
# Add-LocalGroupMember přidá uživatele do lokální skupiny
# ErrorAction SilentlyContinue = nehlásit chybu, pokud už je v skupině
Add-LocalGroupMember -Group "Administrators" -Member "{user['username']}" -ErrorAction SilentlyContinue
"""

        script_content += """
# === VYPNUTÍ IE ENHANCED SECURITY CONFIGURATION ===
# IE ESC znemožňuje surfání na internetu - vypínáme pro testování
Write-Host "Vypínám IE Enhanced Security Configuration..."
# Nastavení registru - IsInstalled=0 vypne ESC
$AdminKey = "HKLM:\\SOFTWARE\\Microsoft\\Active Setup\\Installed Components\\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}"
$UserKey = "HKLM:\\SOFTWARE\\Microsoft\\Active Setup\\Installed Components\\{A509B1A8-37EF-4b3f-8CFC-4F3A74704073}"
Set-ItemProperty -Path $AdminKey -Name "IsInstalled" -Value 0 -Force
Set-ItemProperty -Path $UserKey -Name "IsInstalled" -Value 0 -Force

# === ZOBRAZENÍ INFORMAČNÍHO SOUHRNU ===
Write-Host ""
Write-Host "======================================"
Write-Host "Konfigurace dokončena!"
Write-Host "======================================"
Write-Host ""
Write-Host "IIS Web Server běží na: http://localhost"
Write-Host ""
Write-Host "Uživatelé systému:"
# Výpis všech lokálních uživatelů
Get-LocalUser | Select-Object Name, Enabled | Format-Table

# Ukončení logování
Stop-Transcript

Write-Host "Setup dokončen. Restartování..."

# === VYPNUTÍ AUTOMATICKÉHO PŘIHLÁŠENÍ ===
# Po prvním přihlášení už nechceme auto-login
# Smazání AutoAdminLogon klíče z registru
Remove-ItemProperty -Path "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon" -Name "AutoAdminLogon" -ErrorAction SilentlyContinue

# Odpojení CD jednotky
Write-Host "Odpojuji instalační média..."
"""
        
        return script_content
    
    def create_config_iso(self):
        """
        Vytvoření ISO s konfiguračními soubory a floppy s Autounattend.xml.
        
        Tato metoda připraví 2 média pro VM:
        1. FLOPPY disk - obsahuje Autounattend.xml
           - Windows Setup automaticky hledá Autounattend.xml na A: (floppy)
        2. CONFIG ISO - obsahuje setup.ps1 a webový projekt
           - Připojí se jako F: v VM
        
        Práce s floppy:
        - Vytvoří prázdný floppy image (dd)
        - Naformátuje ho jako FAT (mkfs.vfat)
        - Pomocí sudo mount připojí a zkopíruje Autounattend.xml
        
        Returns:
            tuple: (Path k config ISO, Path k floppy image)
            
        Raises:
            subprocess.CalledProcessError: Při chybě při vytváření médií
        """
        print("Vytvářím konfigurační ISO...")
        
        # Vytvoření dočasné složky pro přípravu souborů pro ISO
        # tempfile.mkdtemp() vytvoří unikátní dočasnou složku v /tmp
        temp_dir = tempfile.mkdtemp()
        
        try:
            # === VYTVOŘENÍ FLOPPY DISKU S AUTOUNATTEND.XML ===
            
            # Vytvoření dočasné složky pro přípravu Autounattend.xml
            floppy_dir = tempfile.mkdtemp()
            autounattend_floppy = Path(floppy_dir) / "Autounattend.xml"
            
            # Zápis vygenerovaného XML do souboru
            with open(autounattend_floppy, 'w', encoding='utf-8') as f:
                f.write(self.generate_autounattend_xml())
            
            # Cesta k výslednému floppy image souboru
            floppy_img = self.work_dir / f"{self.vm_name}_floppy.img"
            
            # Vytvoření prázdného floppy image (1.44MB = 1440 KB)
            # dd if=/dev/zero = vstup jsou samé nuly
            # of=floppy.img = výstup do souboru
            # bs=1024 count=1440 = 1440 bloků po 1024 bytech = 1.44 MB
            subprocess.run(['dd', 'if=/dev/zero', f'of={floppy_img}', 'bs=1024', 'count=1440'], 
                          check=True, capture_output=True)
            
            # Formátování floppy image jako FAT filesystem
            # mkfs.vfat = vytvoření FAT souborového systému (kompatibilní s Windows)
            subprocess.run(['mkfs.vfat', str(floppy_img)], check=True, capture_output=True)
            
            # === PŘIPOJENÍ A ZKOPÍROVÁNÍ AUTOUNATTEND.XML NA FLOPPY ===
            # Vytvoření mount pointu (místo pro připojení)
            mount_point = tempfile.mkdtemp()
            
            try:
                # Připojení floppy image jako loop device (virtuální disk)
                # sudo je potřeba pro mount operaci
                # -o loop = připojit jako loop device (obraz disku)
                subprocess.run(['sudo', 'mount', '-o', 'loop', str(floppy_img), mount_point], 
                              check=True, capture_output=True)
                
                # Zkopírování Autounattend.xml na připojený floppy
                # sudo cp = kopírování s admin právy
                subprocess.run(['sudo', 'cp', str(autounattend_floppy), mount_point], 
                              check=True, capture_output=True)
                
                # Odpojení floppy image
                subprocess.run(['sudo', 'umount', mount_point], check=True, capture_output=True)
            finally:
                # Vyčištění dočasných složek (i při chybě)
                shutil.rmtree(mount_point)
                shutil.rmtree(floppy_dir)
            
            print(f"✓ Floppy image vytvořen: {floppy_img}")
            
            # === VYTVOŘENÍ CONFIG ISO S SETUP.PS1 A WEBOVÝMI SOUBORY ===
            
            # Vytvoření setup.ps1 v dočasné složce
            setup_script_path = Path(temp_dir) / "setup.ps1"
            with open(setup_script_path, 'w', encoding='utf-8') as f:
                f.write(self.generate_setup_script())
            
            # Příprava webového projektu
            web_source = Path(self.config['windows']['web_project']['source_folder']).expanduser()
            web_dest = Path(temp_dir) / "web"  # Cílová složka v ISO: /web
            web_dest.mkdir(exist_ok=True)
            
            # Pokud existuje webový projekt, zkopírovat ho
            if web_source.exists():
                print(f"Kopíruji webový projekt z {web_source}...")
                # Iterace přes všechny položky ve zdrojové složce
                for item in web_source.iterdir():
                    if item.is_file():
                        # Zkopírování jednotlivých souborů
                        shutil.copy2(item, web_dest)  # copy2 zachová metadata
                    elif item.is_dir():
                        # Rekurzivní kopírování složek
                        # dirs_exist_ok=True = nepřepisovat, pokud existuje
                        shutil.copytree(item, web_dest / item.name, dirs_exist_ok=True)
            else:
                # Pokud webový projekt neexistuje, vytvořit základní index.html
                print("Vytvářím základní index.html...")
                index_path = web_dest / "index.html"
                with open(index_path, 'w', encoding='utf-8') as f:
                    # Vygenerování HTML s informacemi z konfigurace
                    f.write(f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.config['windows']['web_project']['name']}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .container {{
            background: rgba(255, 255, 255, 0.1);
            padding: 40px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }}
        h1 {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .info {{
            background: rgba(255, 255, 255, 0.2);
            padding: 20px;
            border-radius: 5px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 {self.config['windows']['web_project']['name']}</h1>
        <p>Vítejte na automaticky nasazeném Windows Server 2022!</p>
        <div class="info">
            <h2>Informace o serveru:</h2>
            <ul>
                <li>Server: {self.config['windows']['computer_name']}</li>
                <li>IIS Web Server: Aktivní</li>
                <li>Datum nasazení: <script>document.write(new Date().toLocaleDateString('cs-CZ'))</script></li>
            </ul>
        </div>
    </div>
</body>
</html>""")
            
            # === VYTVOŘENÍ ISO SOUBORU Z DOČASNÉ SLOŽKY ===
            iso_path = self.work_dir / f"{self.vm_name}_config.iso"
            
            # mkisofs - nástroj pro vytváření ISO 9660 souborových systémů
            cmd = [
                'mkisofs',
                '-o', str(iso_path),    # Output file (cílový ISO soubor)
                '-J',                   # Joliet extensions (dlouhé názvy souborů pro Windows)
                '-r',                   # Rock Ridge extensions (UNIX-like permissions)
                '-V', 'CONFIG',         # Volume label (název svazku)
                str(temp_dir)           # Zdrojová složka k zabalení do ISO
            ]
            
            # Vytvoření ISO souboru
            # capture_output=True = potlačení výstupu do konzole
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"✓ Konfigurační ISO vytvořeno: {iso_path}")
            
            # Návrat cest k oběma vytvořeným médiím
            return iso_path, floppy_img
            
        finally:
            # Vyčištění dočasné složky (i při chybě díky finally bloku)
            # Toto zajistí, že se /tmp nezaplní starými soubory
            shutil.rmtree(temp_dir)
    
    def start_vm(self, disk_path, config_iso_path, floppy_path):
        """
        Spuštění VM pomocí QEMU.
        
        Tato metoda vytvoří QEMU příkaz a spustí virtuální stroj s:
        - Virtuálním diskem (QCOW2)
        - Floppy diskem s Autounattend.xml
        - 3 CD-ROM jednotkami:
          * D: = virtio-win.iso (ovladače)
          * E: = Windows Server ISO (instalační médium)
          * F: = config ISO (setup skripty + web)
        - VNC serverem pro vzdálený přístup
        - Síťovou kartou (NAT nebo bridge podle konfigurace)
        
        Args:
            disk_path (Path): Cesta k virtuálnímu disku
            config_iso_path (Path): Cesta k config ISO
            floppy_path (Path): Cesta k floppy image
            
        Raises:
            SystemExit: Pokud Windows ISO nebo virtio ISO neexistují
        """
        print("Spouštím virtuální stroj...")
        
        # === KONTROLA EXISTENCE ISO SOUBORŮ ===
        
        # Kontrola Windows Server ISO
        iso_path = Path(self.config['vm']['iso_path']).expanduser()
        if not iso_path.exists():
            print(f"CHYBA: ISO soubor nenalezen: {iso_path}")
            sys.exit(1)
        
        # Kontrola VirtIO ovladačů ISO
        virtio_iso = Path(self.config['vm'].get('virtio_iso_path', '~/iso/virtio-win.iso')).expanduser()
        if not virtio_iso.exists():
            print(f"VAROVÁNÍ: virtio-win.iso nenalezen: {virtio_iso}")
            print("Instalace může selhat bez virtio ovladačů")
        
        # === NAČTENÍ PARAMETRŮ Z KONFIGURACE ===
        
        memory = self.config['vm']['memory']                        # Např. "4G"
        cpus = self.config['vm']['cpus']                            # Např. 2
        vnc_port = self.config['vm'].get('vnc_port', 0)            # 0 = port 5900
        network_mode = self.config['vm'].get('network_mode', 'nat') # 'nat' nebo 'bridge'
        bridge_interface = self.config['vm'].get('bridge_interface', 'br0')  # Jen pro bridge
        
        # Síťová konfigurace podle režimu
        if network_mode == 'bridge':
            network_config = f"-netdev bridge,id=net0,br={bridge_interface} -device virtio-net-pci,netdev=net0,mac=52:54:00:12:34:56"
            port_forward_info = f"VM bude mít IP z rozsahu {bridge_interface} sítě"
            requires_sudo = "sudo "
        else:
            # NAT mode s port forwardingem
            port_forwards = self.config['vm'].get('port_forwards', [{'host': 8080, 'guest': 80}])
            
            # Přidání RDP portu, pokud je RDP zapnutý
            rdp_config = self.config['vm'].get('rdp', {})
            if rdp_config.get('enabled', False):
                rdp_host_port = rdp_config.get('host_port', 3389)
                port_forwards.append({'host': rdp_host_port, 'guest': 3389})
            
            hostfwd_rules = ','.join([f"hostfwd=tcp::{pf['host']}-:{pf['guest']}" for pf in port_forwards])
            network_config = f"-net nic,model=virtio -net user,{hostfwd_rules}"
            
            # Info o port forwardingu
            port_forward_lines = [f"localhost:{pf['host']} -> VM:{pf['guest']}" for pf in port_forwards]
            port_forward_info = "Port forwards:  " + ", ".join(port_forward_lines)
            requires_sudo = ""
        
        # Vytvoření run skriptu
        run_script_path = self.work_dir / f"run_{self.vm_name}.sh"
        
        # === SESTAVENÍ QEMU PŘÍKAZU ===
        # qemu-system-x86_64 = QEMU emulátor pro 64-bit x86 architekturu
        # POZNÁMKA: Komentáře NESMÍ být za backslashem (\), musí být na samostatných řádcích!
        qemu_cmd = f"""#!/bin/bash
# Spuštění QEMU virtuálního stroje pro Windows Server 2022
# Tento skript byl automaticky vygenerován pomocí deploy_vm.py

# Název VM (zobrazí se v procesech)
# Q35 chipset s KVM akcelerací (hardware virtualizace)
# CPU hostitele pro nejlepší výkon
# Počet CPU jader: {cpus}
# RAM: {memory}
{requires_sudo}qemu-system-x86_64 \\
    -name "{self.vm_name}" \\
    -machine type=q35,accel=kvm \\
    -cpu host \\
    -smp {cpus} \\
    -m {memory} \\
    -drive file={disk_path},if=virtio,format=qcow2 \\
    -drive file={floppy_path},if=floppy,format=raw \\
    -drive file={virtio_iso},media=cdrom,index=1 \\
    -drive file={iso_path},media=cdrom,index=2 \\
    -drive file={config_iso_path},media=cdrom,index=3 \\
    -boot order=d \\
    -vnc :{vnc_port} \\
    {network_config} \\
    -rtc base=localtime \\
    -usbdevice tablet \\
    "$@"
"""
        
        # Zápis QEMU příkazu do bash skriptu
        with open(run_script_path, 'w') as f:
            f.write(qemu_cmd)
        
        # Nastavení execute oprávnění pro skript (chmod +x)
        # 0o755 = rwxr-xr-x (vlastník může spustit, ostatní jen číst a spustit)
        run_script_path.chmod(0o755)
        
        # === ZOBRAZENÍ INFORMACÍ O VM ===
        # Výpis detailů o připraveném VM pro uživatele
        print(f"""
╔════════════════════════════════════════════════════════════════╗
║              Virtuální stroj je připraven ke spuštění          ║
╠════════════════════════════════════════════════════════════════╣
║ VM Name:       {self.vm_name:<48}                              ║
║ Disk:          {str(disk_path):<48}                            ║
║ Memory:        {memory:<48}                                    ║
║ CPUs:          {cpus:<48}                                      ║
║ VNC Port:      590{vnc_port} (připojte se z Win11)             ║
║ Network:       {network_mode:<48}                              ║
║ {port_forward_info:<62}                                        ║
╠════════════════════════════════════════════════════════════════╣
║ Spuštění VM:                                                   ║
║   {str(run_script_path):<58}                                   ║
║                                                                ║
║ VNC připojení:                                                 ║
║   <IP_serveru>:590{vnc_port}                                   ║
║                                                                ║
║ Po dokončení instalace (15-30 minut):                          ║
║   - Windows se automaticky nainstaluje a nakonfiguruje         ║
║   - IIS Web Server bude dostupný                               ║
║   - Webová stránka: http://localhost:8080                      ║
╚════════════════════════════════════════════════════════════════╝
""")
        
        # === INTERAKTIVNÍ SPUŠTĚNÍ VM ===
        # Zeptat se uživatele, zda chce spustit VM hned teď
        print("\nChcete spustit VM nyní? [y/N]: ", end='')
        response = input().strip().lower()
        
        if response == 'y':
            print("\nSpouštím VM v pozadí...")
            
            # Cesta k log souboru pro zachycení výstupu QEMU
            log_file = self.work_dir / f"{self.vm_name}_qemu.log"
            
            # Spuštění VM jako background proces
            with open(log_file, 'w') as log:
                # subprocess.Popen() spustí proces a ihned se vrátí (na rozdíl od .run())
                subprocess.Popen(
                    [str(run_script_path)],  # Spuštění bash skriptu
                    stdout=log,              # Přesměrování stdout do log souboru
                    stderr=log,              # Přesměrování stderr do log souboru
                    cwd=str(self.work_dir)  # Pracovní adresář = work_dir
                )
            
            print(f"VM spuštěn, log: {log_file}")
            print(f"Připojte se přes VNC na port 590{vnc_port}")
        else:
            # Uživatel nechce spustit hned - ukázat jak spustit později
            print(f"\nVM můžete spustit později pomocí: {run_script_path}")
        
        # === VYTVOŘENÍ BOOT SKRIPTU (pro restart již nainstalovaného systému) ===
        # Tento skript bootuje z disku místo z CD-ROM
        boot_script_path = self.work_dir / f"boot_{self.vm_name}.sh"
        
        # QEMU příkaz pro boot z disku (bez instalačních médií)
        boot_cmd = f"""#!/bin/bash
# Spuštění již nainstalovaného Windows serveru
# Bootuje z virtuálního disku, nepřipojuje instalační ISO

{requires_sudo}qemu-system-x86_64 \\
    -name "{self.vm_name}" \\
    -machine type=q35,accel=kvm \\
    -cpu host \\
    -smp {cpus} \\
    -m {memory} \\
    -drive file={disk_path},if=virtio,format=qcow2 \\
    -boot c \\
    -vnc :{vnc_port} \\
    {network_config} \\
    -rtc base=localtime \\
    -usbdevice tablet \\
    "$@"
"""
        
        # Zápis boot skriptu
        with open(boot_script_path, 'w') as f:
            f.write(boot_cmd)
        
        # Nastavení execute oprávnění
        boot_script_path.chmod(0o755)
        
        print(f"\nPro restart po instalaci použijte: {boot_script_path}")
    
    def deploy(self):
        """
        Hlavní metoda pro deployment - orchestruje celý proces.
        
        Tato metoda postupně zavolá všechny kroky deploymentu:
        1. Kontrola závislostí (QEMU, mkisofs, atd.)
        2. Vytvoření virtuálního disku
        3. Generování konfiguračních souborů (Autounattend.xml, setup.ps1)
        4. Vytvoření config ISO a floppy image
        5. Spuštění VM
        
        Toto je hlavní vstupní bod pro celý proces automatizovaného deploymentu.
        """
        # Úvodní banner
        print(f"""
╔════════════════════════════════════════════════════════════════╗
║        Windows Server VM Deployment - QEMU/KVM                 ║
╚════════════════════════════════════════════════════════════════╝
""")
        
        # Provedení všech kroků deploymentu v pořadí
        self.check_dependencies()                      # 1. Kontrola závislostí
        disk_path = self.create_disk_image()          # 2. Vytvoření disku
        config_iso, floppy_img = self.create_config_iso()  # 3. Příprava config médií
        self.start_vm(disk_path, config_iso, floppy_img)   # 4. Spuštění VM
        
        print("\nDeployment dokončen!")


def main():
    """
    Hlavní funkce programu - vstupní bod při spuštění ze příkazové řádky.
    
    Parsuje argumenty příkazové řádky (config.yaml cesta) a spustí deployment.
    Používá argparse pro profesionální zpracování CLI argumentů s nápovědou.
    """
    # Vytvoření argument parseru s popisem a příklady
    parser = argparse.ArgumentParser(
        description='Automatické nasazení Windows Server VM',
        formatter_class=argparse.RawDescriptionHelpFormatter,  # Zachová formátování v epilogu
        epilog="""
Příklad použití:
  python3 deploy_vm.py config.yaml
  
Poznámky:
  - ISO soubor Windows Serveru musí existovat na cestě uvedené v config.yaml
  - Skript vyžaduje sudo oprávnění pro KVM
  - VNC server bude dostupný na portu 5900 + vnc_port z konfigurace
        """
    )
    
    # Definice povinného argumentu - cesta k config.yaml
    parser.add_argument('config', help='Cesta ke konfiguračnímu YAML souboru')
    
    # Parsování argumentů z příkazové řádky
    args = parser.parse_args()
    
    # Kontrola existence konfiguračního souboru
    if not os.path.exists(args.config):
        print(f"CHYBA: Konfigurační soubor nenalezen: {args.config}")
        sys.exit(1)
    
    # Vytvoření instance deployeru a spuštění deploymentu
    deployer = WindowsVMDeployer(args.config)
    deployer.deploy()


# Python standard - spustit main() pouze pokud je soubor spuštěn přímo
# (ne když je importován jako modul)
if __name__ == "__main__":
    main()
