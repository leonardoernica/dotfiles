# Wi-Fi no Hyprland

A central cria perfis pessoais (`connection.permissions=user:<usuário>`).
O NetworkManager salva os perfis e senhas em arquivos protegidos pelo sistema.
A edição de perfis pessoais não exige autenticação de administrador. Não é
necessário liberar sudo nem instalar regras permissivas no Polkit.

O painel localiza perfis pelo SSID e ativa pelo UUID. Senhas seguem pelo D-Bus,
sem aparecer nos argumentos dos processos. Ao substituir a senha de um perfil
compartilhado, cria um perfil pessoal e preserva o original. Perfis pessoais
existentes são atualizados, sem gerar duplicatas a cada tentativa.

`nm-applet --indicator` inicia com o Hyprland e fornece o agente de segredos para
as ferramentas de rede. O agente do Polkit continua responsável por operações
administrativas. Redes empresariais/802.1X e WEP abrem o editor avançado.

## Realtek RTL8821CE: economia de energia

Use a correção quando os logs mostrarem falhas do rtw88, como
`firmware failed to ack driver for leaving Deep Power mode`:

```bash
sudo ./network/install-realtek-stability.sh
```

O script verifica o driver, faz backup, desativa economia Wi-Fi para o
`rtw88_8821ce` e desativa o modo profundo do `rtw88_core`. A configuração
persiste após reiniciar. Não reinicia NetworkManager nem troca a rede.
A bateria pode durar um pouco menos.

```bash
iw dev wlo1 get power_save
cat /sys/module/rtw88_core/parameters/disable_lps_deep
```

A saída esperada é `Power save: off` e `Y`. Ajuste o nome do adaptador se necessário.

## Diagnóstico

```bash
nmcli general permissions
nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS device show wlo1
sudo journalctl -b -u NetworkManager -u wpa_supplicant --since '-10 minutes'
sudo journalctl -b -k | rg 'rtw88|Deep Power|wlo1'
```

`WRONG_KEY` indica rejeição da credencial ou falha de negociação do handshake.
`Key negotiation completed` seguido de falha em `ip-config` indica que a senha
passou, mas a configuração IP não terminou. Aguarde o DHCP antes de tentar de novo.
Prefira WPA2 com AES/CCMP ou WPA3 no roteador; o modo misto WPA1/WPA2 pode negociar
TKIP para tráfego de grupo mesmo usando CCMP na chave individual.

## Testes

```bash
PYTHONPATH=waybar/waybar/scripts python -m unittest discover -s tests -v
```
