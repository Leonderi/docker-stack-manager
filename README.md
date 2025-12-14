# Docker Stack Manager

Eine TUI-Anwendung (Terminal User Interface) zur Verwaltung von Docker-Stacks auf mehreren VMs/LXC-Containern mit Traefik als Reverse Proxy.

## Features

- **VM/LXC Management**: Erstellen und verwalten von LXC-Containern via Proxmox API
- **Automatische Initialisierung**: Setup-Script für neue Container (User, SSH, Docker, Firewall)
- **Traefik Integration**: Automatisches Routing und SSL-Zertifikate
- **Stack Deployment**: Docker Compose Stacks auf VMs deployen
- **SSH Key Management**: Automatische Generierung und Verwaltung von SSH-Keys

## Installation

```bash
# Repository klonen
git clone <repository-url>
cd docker-traefik-app

# Virtual Environment erstellen
python3 -m venv venv
source venv/bin/activate

# Dependencies installieren
pip install -r requirements.txt

# Anwendung starten
python main.py
```

## Erste Schritte

1. **Settings konfigurieren**
   - IP-Settings (Subnet, Gateway, DNS)
   - Proxmox-Verbindung einrichten
   - Domain und SSL konfigurieren

2. **Proxmox API Token erstellen** (siehe unten)

3. **LXC Container erstellen**
   - VM Manager → Create LXC
   - Container nach Erstellung initialisieren

4. **Stacks deployen**
   - Stack auswählen und auf VM deployen

---

## Proxmox API Token einrichten

### Schnellstart mit Root-Token

1. **Proxmox Web-UI öffnen**: `https://<proxmox-ip>:8006`

2. **Token erstellen**:
   - `Datacenter` → `Permissions` → `API Tokens` → `Add`

   | Feld | Wert |
   |------|------|
   | User | `root@pam` |
   | Token ID | `docker-manager` |
   | **Privilege Separation** | **DEAKTIVIERT** |

3. **Secret speichern** - wird nur einmal angezeigt!

4. **In der App konfigurieren** (Settings → Proxmox):

   | Feld | Wert |
   |------|------|
   | Host | `192.168.1.10` |
   | Port | `8006` |
   | User | `root@pam` |
   | Token Name | `docker-manager` |
   | Token Value | `<das-secret>` |
   | Verify SSL | aus (bei selbstsigniertem Zertifikat) |

---

### Eingeschränkter API Token (empfohlen für Produktion)

Für mehr Sicherheit kann ein dedizierter Benutzer mit minimalen Rechten erstellt werden.

#### Schritt 1: Benutzer anlegen

```
Datacenter → Permissions → Users → Add
```

| Feld | Wert |
|------|------|
| User name | `dockermgr` |
| Realm | `Proxmox VE authentication server` |
| Password | (beliebig, wird nicht benötigt) |
| Enabled | ✓ |

#### Schritt 2: Rolle mit minimalen Rechten erstellen

```
Datacenter → Permissions → Roles → Create
```

| Feld | Wert |
|------|------|
| Name | `DockerManager` |

**Benötigte Privileges auswählen:**

| Privilege | Beschreibung |
|-----------|--------------|
| `Datastore.AllocateSpace` | Speicherplatz für Container |
| `Datastore.AllocateTemplate` | Templates verwenden |
| `Datastore.Audit` | Storage-Info lesen |
| `Pool.Audit` | Pool-Info lesen (optional) |
| `Sys.Audit` | System-Info lesen |
| `Sys.Modify` | Cluster-Operationen |
| `VM.Allocate` | VMs/Container erstellen |
| `VM.Audit` | VM-Info lesen |
| `VM.Clone` | VMs/Container klonen |
| `VM.Config.CPU` | CPU konfigurieren |
| `VM.Config.Disk` | Disks konfigurieren |
| `VM.Config.Memory` | RAM konfigurieren |
| `VM.Config.Network` | Netzwerk konfigurieren |
| `VM.Config.Options` | Optionen konfigurieren |
| `VM.Console` | Konsole öffnen |
| `VM.PowerMgmt` | Start/Stop/Restart |

#### Schritt 3: Berechtigung zuweisen

```
Datacenter → Permissions → Add
```

| Feld | Wert |
|------|------|
| Path | `/` |
| User | `dockermgr@pve` |
| Role | `DockerManager` |
| Propagate | ✓ |

#### Schritt 4: API Token erstellen

```
Datacenter → Permissions → API Tokens → Add
```

| Feld | Wert |
|------|------|
| User | `dockermgr@pve` |
| Token ID | `docker-manager` |
| **Privilege Separation** | **DEAKTIVIERT** |

**Secret sicher speichern!**

#### Schritt 5: In der App konfigurieren

| Feld | Wert |
|------|------|
| User | `dockermgr@pve` |
| Token Name | `docker-manager` |
| Token Value | `<das-secret>` |

---

### CLI: Token per Kommandozeile erstellen

```bash
# Auf dem Proxmox-Server als root:

# Benutzer anlegen
pveum user add dockermgr@pve

# Rolle erstellen
pveum role add DockerManager -privs "Datastore.AllocateSpace,Datastore.AllocateTemplate,Datastore.Audit,Sys.Audit,Sys.Modify,VM.Allocate,VM.Audit,VM.Clone,VM.Config.CPU,VM.Config.Disk,VM.Config.Memory,VM.Config.Network,VM.Config.Options,VM.Console,VM.PowerMgmt"

# Berechtigung zuweisen
pveum aclmod / -user dockermgr@pve -role DockerManager

# API Token erstellen (ohne Privilege Separation)
pveum user token add dockermgr@pve docker-manager --privsep 0

# Ausgabe enthält das Secret - speichern!
```

---

## Fehlerbehebung

### Proxmox-Verbindung

| Fehler | Lösung |
|--------|--------|
| `401 Unauthorized` | Token Name/Value prüfen, User-Format: `root@pam` |
| `403 Permission Denied` | "Privilege Separation" deaktivieren |
| `Connection refused` | Port 8006 und Firewall prüfen |
| `SSL Error` | "Verify SSL" deaktivieren |

### LXC Container

| Fehler | Lösung |
|--------|--------|
| Kein Template | Template in Proxmox herunterladen |
| Container startet nicht | Logs in Proxmox prüfen |
| SSH Verbindung fehlgeschlagen | IP und SSH-Key prüfen |

### Initialisierung

| Fehler | Lösung |
|--------|--------|
| `Permission denied` | Root-SSH-Key prüfen |
| `apt update failed` | DNS-Einstellungen prüfen |
| Docker Installation fehlgeschlagen | Container hat nesting=1? |

---

## Projektstruktur

```
docker-traefik-app/
├── main.py                 # Einstiegspunkt
├── requirements.txt        # Python Dependencies
├── config/                 # Konfigurationsdateien
│   ├── settings.yaml       # Globale Einstellungen
│   ├── vms.yaml           # VM-Konfigurationen
│   └── ssh_keys/          # Generierte SSH-Keys
├── src/
│   ├── core/              # Business Logic
│   │   ├── config_loader.py
│   │   ├── ssh_manager.py
│   │   ├── ssh_keygen.py
│   │   ├── proxmox_api.py
│   │   ├── lxc_manager.py
│   │   ├── docker_manager.py
│   │   └── traefik_manager.py
│   └── tui/               # Terminal UI
│       ├── app.py
│       └── screens/
│           ├── dashboard.py
│           ├── settings.py
│           ├── vm_manager.py
│           ├── lxc_create.py
│           └── ...
├── templates/             # Docker Compose Templates
└── docs/                  # Dokumentation
```

---

## VM Initialisierung

Nach dem Erstellen eines LXC-Containers muss dieser initialisiert werden. Das Setup-Script führt folgende Schritte aus:

1. **System aktualisieren**
   ```bash
   apt update && apt upgrade -y
   ```

2. **Basis-Pakete installieren**
   ```bash
   apt install -y sudo curl wget git ca-certificates gnupg ufw
   ```

3. **Manager-User anlegen**
   ```bash
   useradd -m -s /bin/bash -G sudo manager
   echo "manager ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/manager
   ```

4. **SSH-Key einrichten**
   - Neuer Key wird generiert: `config/ssh_keys/<hostname>_manager`
   - Key wird für User `manager` installiert

5. **Root sperren**
   ```bash
   passwd -l root
   # PermitRootLogin no
   # PasswordAuthentication no
   ```

6. **Firewall konfigurieren**
   ```bash
   ufw allow 22/tcp   # SSH
   ufw allow 80/tcp   # HTTP
   ufw allow 443/tcp  # HTTPS
   ufw enable
   ```

7. **Docker installieren**
   ```bash
   curl -fsSL https://get.docker.com | sh
   usermod -aG docker manager
   ```

---

## Lizenz

MIT License
