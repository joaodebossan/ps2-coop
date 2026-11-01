# PS2 Co-op

Plataforma local para jogar **qualquer jogo de PS2 com co-op** (1 a 4 jogadores) com amigos, usando o PCSX2 e o MoonlightWeb. Coloque o app na pasta do jogo, execute uma vez e ele prepara o resto: baixa o emulador, instala o servidor de streaming, importa a BIOS que já estiver no PC, configura os controles e cria o ícone na área de trabalho.

O projeto é um **app local** com interface no navegador, escrito só com a biblioteca padrão do Python. Para o usuário final ele é distribuído como **um único arquivo**: `PS2Coop.exe` no Windows ou `PS2Coop-x86_64.AppImage` no Linux. Coloque esse arquivo na pasta do jogo e dê dois cliques — não precisa extrair, copiar pastas nem instalar Python.

---

## O que ele faz

- Encontra `.iso`, `.chd` e `.cso` na pasta em que foi executado.
- Baixa o **PCSX2 portátil** (AppImage no Linux, instalador silencioso no Windows).
- Instala o **MoonlightWeb** no PC anfitrião:
  - Linux: `.deb` em Debian/Ubuntu/Mint/Pop/Zorin/Kali; `.rpm` em Fedora/RHEL/Rocky/Alma/Nobara/openSUSE.
  - Windows: instalador x64/ARM64.
- Importa automaticamente uma **BIOS** já usada por outro PCSX2 (Flatpak, Snap, instalação normal ou portátil). Se não achar, pede o arquivo `.bin` do seu console.
- Configura **1 a 4 controles** no PCSX2, incluindo multitap para 3–4 jogadores.
- Mapeia o controle físico do host como jogador 1 quando o modo **Host local** está ligado.
- Gera convites individuais no MoonlightWeb: cada amigo recebe **um link + um PIN**.
- Inicia o PCSX2 em tela cheia quando você clica em **Iniciar jogo**, já com os convidados conectados e os controles mapeados.
- Faz **backup automático do memory card** ao parar o jogo; permite restaurar backups antigos.
- Cria o **ícone na área de trabalho** e no menu de aplicativos.
- Tem **tema claro, tema escuro acinzentado e modo sistema**.
- Não envia telemetria e só escuta em `127.0.0.1`.

> BIOS e ISOs **não** são baixadas nem distribuídas. Use a BIOS extraída do seu próprio console e cópias dos seus próprios jogos. O app é só a ferramenta de preparação e conexão.

---

## Requisitos

### Windows

- Windows 10 ou 11, x64 ou ARM64.
- Baixe **`PS2Coop.exe`**; não precisa ter Python instalado.
- Aceite o aviso do Windows/UAC quando o instalador do PCSX2 ou do MoonlightWeb pedir permissão.

### Linux

- Distribuição x64: Ubuntu 22.04+, Debian 12+, Fedora 36+, Mint 21+, Pop!\_OS etc.
- Baixe **`PS2Coop-x86_64.AppImage`**; não precisa ter Python instalado.
- Na primeira vez, dê permissão de execução ao arquivo (Propriedades → Permitir execução, ou `chmod +x PS2Coop-x86_64.AppImage`). Depois é só dois cliques.
- Se o AppImage não abrir por falta de FUSE: instale `libfuse2`/`libfuse2t64` ou rode `APPIMAGE_EXTRACT_AND_RUN=1 ./PS2Coop-x86_64.AppImage`.
- No Debian/Ubuntu, o MoonlightWeb nativo precisa de instalação via `.deb` (o app faz isso com `pkexec`/`sudo`; aparecerá uma janela de autorização).
- No Arch/Manjaro/Endeavour/Garuda, instale o MoonlightWeb pelo AUR (`paru -S moonlightweb-bin`) e clique em **Preparar** de novo.
- Em sistemas imutáveis (Bazzite, SteamOS, Fedora Silverblue/Kinoite), use o guia oficial do MoonlightWeb para instalar em camada; o app avisa e não tenta forçar o gerenciador de pacotes.

---

## Baixar e jogar (um arquivo só)

1. Baixe o release mais recente: **[github.com/joaodebossan/ps2-coop/releases/latest](https://github.com/joaodebossan/ps2-coop/releases/latest)**.
   - **Windows:** `PS2Coop.exe`
   - **Linux:** `PS2Coop-x86_64.AppImage`
2. Coloque o arquivo **na mesma pasta da ISO/CHD/CSO**. Não extraia nada.
3. Abra com **dois cliques**.
   - Linux: na primeira vez, marque “Permitir execução” ou rode `chmod +x PS2Coop-x86_64.AppImage`.
4. O navegador abre o portal. A preparação começa sozinha: PCSX2, MoonlightWeb, BIOS, controles e atalho.
5. Se a BIOS não for encontrada, envie o `.bin` na etapa **BIOS do PS2**.
6. Escolha quantos jogadores, ligue/desligue **Host local** e clique em **1. Convidar amigos**.
7. Envie link e PIN para cada amigo. Cada um abre o link, digita o PIN e aperta um botão no controle.
8. Quando todos aparecerem como **conectado**, clique em **3. Iniciar jogo**.

O ícone na área de trabalho abre o mesmo portal e já encontra o servidor em execução. Depois da primeira preparação, você pode abrir o jogo só pelo ícone.

> O usuário final nunca precisa ver `app.py`, `ps2coop/`, `web/` ou `iniciar.*`: isso é só para desenvolvimento. O release entrega um único executável/AppImage.

## Rodar do código-fonte (desenvolvimento)

1. Crie uma pasta para o jogo, por exemplo `~/Jogos/TimeSplitters 2`.
2. Copie para ela a ISO/CHD/CSO e os arquivos do projeto (`app.py`, `ps2coop/`, `web/`, `assets/`, `iniciar.*`; `runtime/` se já existir).
3. Tenha Python 3.10+ e execute:
   - **Windows:** `iniciar.bat`
   - **Linux:** `./iniciar.sh`
4. Para apontar outra pasta de jogos:

```bash
python3 app.py --game "/caminho/da/pasta/do/jogo"
```

No Windows: `iniciar.bat --game "D:\Jogos\Meu Jogo"`.

### Pacotes de desenvolvimento

`make package` (ou `python3 tools/package.py`) gera em `dist/`:

- **`PS2Coop-Windows.zip`** — fonte + `iniciar.bat`; se o Windows não tiver Python, o `.bat` baixa uma cópia portátil.
- **`PS2Coop-Linux.tar.gz`** — fonte + `iniciar.sh` + o binário `ps2coop-bin` quando ele existe.

O executável único usado no release é gerado com `python3 build.py`; o AppImage, com `bash tools/build_appimage.sh`.

---

## Fluxo de uma sessão

O PCSX2 precisa enxergar os controles **antes do boot**, então a ordem importa:

```
convidar  →  amigos entram e conectam o controle  →  iniciar jogo
```

> Enquanto um convite estiver ativo, o convidado vê a tela do seu PC — inclusive a área de trabalho antes de o jogo iniciar. Feche janelas privadas, use um convite por pessoa e clique em **Revogar** quando terminar.

- **Host local ligado**: você joga no PC com um controle físico; cada amigo ocupa um controle virtual.
- **Host local desligado**: todos os jogadores entram pelo navegador (o PC só hospeda a tela e o emulador).
- O botão **Iniciar jogo** fica bloqueado se faltar convidado ou controle. Marque **“Iniciar mesmo assim”** apenas para testar.
- O modo **1 jogador** não gera convites.
- Cada **pasta** tem seu próprio perfil, memory cards e configuração dentro de `.ps2coop/`. Use uma pasta por jogo. Se houver mais de uma ISO na mesma pasta, o seletor troca a imagem, mas o memory card continua sendo o da pasta.

---

## Tema claro e escuro

No topo e em **Preferências → Tema** você escolhe:

- **Sistema** — segue o tema do sistema operacional;
- **Claro** — fundo quente, tipo papel;
- **Escuro** — cinza grafite, não preto puro.

A escolha fica salva no navegador (`localStorage`). O tema não muda o PCSX2.

---

## Rede e ports

O portal do PS2 Co-op usa só `127.0.0.1` (porta `8090`, ou outra livre). Quem precisa de portas é o MoonlightWeb:

- **HTTPS** na porta configurada (padrão `443`; algumas instalações usam `8443`);
- **HTTP** na porta configurada (padrão `80`);
- **UDP 48550–48573** para o vídeo WebRTC (quando o Windows Firewall/roteador pedir).

O app mostra os links de LAN e público no card **Conexão**. O link público é criado pelo **Internet Access** do MoonlightWeb (Admin). Para jogar fora de casa, ative essa opção; se a operadora usar CGNAT/double NAT, use uma VPN como Tailscale.

O QR code não é gerado para não enviar seus links a serviços externos; use os botões **Copiar**.

---

## Segurança e privacidade

- O portal só escuta em loopback. Não fica exposto na rede local.
- Requisições de escrita exigem token de sessão, origem local e Host local; um site malicioso não consegue iniciar/parar jogos nem abrir pastas.
- O token do portal é aleatório por execução e vai embutido no HTML local.
- Links de convite são protegidos pelo PIN do MoonlightWeb; o PIN é mostrado separado do link de propósito.
- Nenhum dado é enviado para servidores nossos. PCSX2 e MoonlightWeb têm suas próprias políticas; o MoonlightWeb tem telemetria opcional configurável no Admin dele.

---

## Solução de problemas

### “Falta a BIOS do PS2”

O app não pode baixar BIOS. Se você já usa PCSX2 (inclusive Flatpak), ele tenta importar de:

- `~/.config/PCSX2/bios`
- `~/.local/share/PCSX2/bios`
- `~/.var/app/net.pcsx2.PCSX2/config/PCSX2/bios`
- `~/snap/pcsx2/current/...`
- `%APPDATA%\PCSX2\bios` / `Documentos\PCSX2\bios` no Windows
- pastas indicadas pelo `PCSX2.ini` de uma instalação existente

Se não encontrar, envie o `.bin` de 1–8 MB na etapa de BIOS. A BIOS deve ser do seu próprio console.

### “O AppImage não captura a tela local”

Isso é uma limitação do MoonlightWeb portátil no Linux: ele só transmite hosts pareados. O app detecta isso e tenta instalar o pacote `.deb`/`.rpm` nativo. No Arch/Manjaro/Bazzite/SteamOS, instale `moonlightweb-bin` pelo AUR.

### O jogo abre sem os controles

1. Gere os convites e peça para cada amigo abrir o link e **apertar um botão** no controle.
2. Espere o status mudar para **conectado**.
3. Só então clique em **Iniciar jogo**.

Se ainda faltar controle no Linux, confira se o MoonlightWeb criou os dispositivos `js*` (veja `/proc/bus/input/devices`). No modo host local, conecte o controle físico antes de abrir o app.

### O vídeo não abre fora de casa

- Ative **Internet Access** no Admin do MoonlightWeb.
- Libere UDP 48550–48573 no firewall/roteador.
- Se a operadora usa CGNAT, use Tailscale ou uma VPN equivalente.
- O link de LAN só funciona no mesmo roteador.

### Windows SmartScreen / UAC

O executável não é assinado. Se o Windows mostrar “aplicativo desconhecido”, clique em **Mais informações → Executar assim mesmo**. O UAC aparece porque o PCSX2/MoonlightWeb instalam drivers e regras de firewall.

### O app não abre / porta ocupada

O portal tenta a porta `8090` e, se estiver ocupada, uma porta livre. Se a janela do navegador não abrir, execute o app pelo terminal (`./PS2Coop-x86_64.AppImage --no-browser` ou `PS2Coop.exe --no-browser`) e abra o endereço impresso.

### Logs

- PCSX2: `pasta_do_jogo/.ps2coop/logs/pcsx2.log`
- MoonlightWeb: `runtime/logs/moonlight.log`
- Pasta de logs: botão **Abrir logs** em Preferências.

---

## Compilar os arquivos únicos

```bash
python3 -m pip install -r requirements-build.txt
python3 build.py
```

Saída:

- Linux: `dist/ps2coop`
- Windows: `dist/ps2coop.exe`

Para gerar o AppImage do Linux:

```bash
bash tools/build_appimage.sh
# dist/PS2Coop-x86_64.AppImage
```

No Windows, o release renomeia `ps2coop.exe` para **`PS2Coop.exe`**. O executável embute `web/` e `assets/`; `runtime/` é criado ao lado dele na primeira execução e guarda PCSX2/MoonlightWeb/logs.

Os workflows em `.github/workflows/`:
- `build.yml` testa e compila nos dois sistemas a cada push.
- `release.yml` é disparado por uma tag `v*` e publica `PS2Coop.exe` + `PS2Coop-x86_64.AppImage` no GitHub Releases.

---

## Testes

```bash
python3 -m unittest discover -s tests -v
```

Cobrem descoberta de jogos, perfil, INI/pads do PCSX2, BIOS, detecção/mapeamento de controles, atalhos com espaços no caminho, downloads com retomada/checksum, integração de convites do MoonlightWeb, API local e proteções de token/Host/Origem.

---

## Estrutura

```
app.py                  entrada do portal (código-fonte)
PS2Coop.exe             release Windows: um arquivo só
PS2Coop-x86_64.AppImage release Linux: um arquivo só
ps2coop/
  app.py                servidor HTTP, API, auto setup, segurança
  pcsx2.py              instalação, BIOS, INI, pads, execução
  moonlight.py          instalação, portas, API de convites, links
  gamepads.py           detecção e mapeamento físico/virtual
  desktop.py            atalhos .lnk/.desktop
  downloads.py          downloads com retomada/checksum e jobs
  saves.py              backup/restauração do memory card
  config.py             caminhos, perfil, utilidades
web/                    interface (HTML/CSS/JS, tema)
assets/                 ícones PNG/ICO/SVG
tools/                  ícones, AppImage, pacotes e bootstrap do Python Windows
tests/                  testes unitários
iniciar.bat/.sh         inicialização pelo código-fonte (desenvolvimento)
build.py                empacotamento PyInstaller
```

---

## Limites conhecidos

- O app não cria patches de co-op para jogos que não têm multiplayer; ele só conecta controles e tela.
- A compatibilidade de cada jogo é a do PCSX2. Jogos com problemas no emulador continuam com problemas.
- O MoonlightWeb transmite a tela do PC; para melhor latência, use cabo ou Wi-Fi 5/6 e mantenha o jogo em resolução nativa do PS2.
- Em PCs com vários monitores, o convite usa a tela principal (Display 1). Deixe o PCSX2 em tela cheia nesse monitor; se quiser transmitir outro, escolha a tela no painel do host do MoonlightWeb.
- No Linux, a captura de tela do MoonlightWeb depende do pacote nativo e do compositor (KMS ou portal ScreenCast).
- macOS não é alvo oficial desta versão.

---

## Créditos

- [PCSX2](https://pcsx2.net) — emulador de PS2 (GPL/LGPL).
- [MoonlightWeb](https://moonlightweb.top) — hospedagem/streaming no navegador (GPLv3).
- Este app é um integrador local independente, sem afiliação com os dois projetos.

Licença do PS2 Co-op: MIT (veja `LICENSE`). Os componentes baixados mantêm suas próprias licenças.
