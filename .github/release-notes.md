# PS2 Co-op — um arquivo só

Baixe **um** arquivo abaixo e coloque na mesma pasta da sua ISO/CHD/CSO:

| Plataforma | Arquivo |
|---|---|
| Windows 10/11 x64 ou ARM64 | **`PS2Coop.exe`** |
| Linux x64 | **`PS2Coop-x86_64.AppImage`** |

## Como usar

1. Baixe o arquivo da sua plataforma.
2. Coloque-o na pasta do jogo, junto da ISO/CHD/CSO.
3. Abra com dois cliques.
   - **Linux:** na primeira vez, permita execução (`chmod +x PS2Coop-x86_64.AppImage` ou Propriedades → Permitir execução). Depois é só dois cliques.
   - **Windows:** se aparecer o SmartScreen, clique em **Mais informações → Executar assim mesmo**. O UAC aparece porque o PCSX2/MoonlightWeb instalam drivers e firewall.
4. O navegador abre o portal. O app baixa o PCSX2, instala o MoonlightWeb, importa a BIOS que já existir, configura os controles e cria o ícone na área de trabalho.

O primeiro uso baixa cerca de 100 MB (PCSX2 + MoonlightWeb). Não é preciso instalar Python nem extrair nada.

## Importante

- **BIOS e ISOs não são incluídas.** Use a BIOS do seu próprio console e cópias dos seus jogos.
- Para jogar fora de casa, ative o **Internet Access** no Admin do MoonlightWeb.
- No Linux, se o AppImage não abrir por falta de FUSE, instale `libfuse2`/`libfuse2t64` ou rode `APPIMAGE_EXTRACT_AND_RUN=1 ./PS2Coop-x86_64.AppImage`.
- No Arch/Manjaro/Endeavour/Garuda, instale o MoonlightWeb pelo AUR (`paru -S moonlightweb-bin`) quando o app pedir.

Código-fonte, guia completo e solução de problemas: https://github.com/joaodebossan/ps2-coop
