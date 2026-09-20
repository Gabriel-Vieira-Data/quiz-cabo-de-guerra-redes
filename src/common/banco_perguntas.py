"""
banco_perguntas.py — Fonte das perguntas de redes usadas no quiz.

Cada pergunta é um dict: {"pergunta": str, "opcoes": [str x4], "resposta_correta": str}.
Tenta carregar de data/perguntas_redes.json; se o arquivo não existir, usa um
banco embutido (_perguntas_padrao) — assim o jogo funciona sem configuração.
"""
import random
from pathlib import Path


class BancoPerguntas:
    def __init__(self, caminho_arquivo: str | None = None):
        # Por padrão, procura o JSON em <projeto>/data/perguntas_redes.json.
        if caminho_arquivo is None:
            base_dir = Path(__file__).resolve().parent.parent
            caminho_arquivo = base_dir / "data" / "perguntas_redes.json"

        self.caminho_arquivo = Path(caminho_arquivo)
        self._perguntas = self._carregar_perguntas()

    def _carregar_perguntas(self):
        """Carrega do arquivo JSON, ou cai no banco embutido se ele não existir."""
        if not self.caminho_arquivo.exists():
            return self._perguntas_padrao()

        import json

        with self.caminho_arquivo.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        # Aceita tanto uma lista direta quanto {"perguntas": [...]}.
        if isinstance(dados, list):
            return dados

        return dados.get("perguntas", [])

    def _perguntas_padrao(self):
        return [
            {
                "pergunta": "Qual protocolo é orientado à conexão?",
                "opcoes": ["TCP", "UDP", "ICMP", "ARP"],
                "resposta_correta": "TCP",
            },
            {
                "pergunta": "Qual camada da pilha TCP/IP é responsável pelo roteamento?",
                "opcoes": ["Camada de rede", "Camada de enlace", "Camada de transporte", "Camada de aplicação"],
                "resposta_correta": "Camada de rede",
            },
            {
                "pergunta": "Qual endereço IP é do tipo broadcast?",
                "opcoes": ["255.255.255.255", "127.0.0.1", "10.0.0.1", "192.168.0.1"],
                "resposta_correta": "255.255.255.255",
            },
            {
                "pergunta": "Qual protocolo é usado para resolver nomes de domínio em endereços IP?",
                "opcoes": ["DNS", "SMTP", "FTP", "DHCP"],
                "resposta_correta": "DNS",
            },
            {
                "pergunta": "Qual porta é comumente usada para HTTPS?",
                "opcoes": ["443", "21", "80", "25"],
                "resposta_correta": "443",
            },
            {
                "pergunta": "Qual protocolo é usado para enviar e-mails?",
                "opcoes": ["SMTP", "HTTP", "SNMP", "POP3"],
                "resposta_correta": "SMTP",
            },
            {
                "pergunta": "Qual utilitário verifica a rota entre dois hosts?",
                "opcoes": ["tracert", "ping", "nslookup", "arp"],
                "resposta_correta": "tracert",
            },
            {
                "pergunta": "Qual camada do modelo OSI trata de endereçamento lógico e roteamento?",
                "opcoes": ["Rede", "Aplicação", "Transporte", "Física"],
                "resposta_correta": "Rede",
            },
            {
                "pergunta": "Qual protocolo faz a atribuição dinâmica de IPs?",
                "opcoes": ["DHCP", "FTP", "HTTP", "DNS"],
                "resposta_correta": "DHCP",
            },
            {
                "pergunta": "Qual camada do modelo OSI encapsula frames?",
                "opcoes": ["Enlace", "Aplicação", "Sessão", "Apresentação"],
                "resposta_correta": "Enlace",
            },
            {
                "pergunta": "Qual comando do Windows exibe a tabela ARP?",
                "opcoes": ["arp -a", "ipconfig", "route print", "netstat"],
                "resposta_correta": "arp -a",
            },
            {
                "pergunta": "Qual protocolo é usado para transferência de arquivos?",
                "opcoes": ["FTP", "DNS", "SSH", "NTP"],
                "resposta_correta": "FTP",
            },
            {
                "pergunta": "Qual tipo de rede usa 10.0.0.0/8 como faixa privada?",
                "opcoes": ["Classe A", "Classe B", "Classe C", "Classe D"],
                "resposta_correta": "Classe A",
            },
            {
                "pergunta": "Qual porta é comum para SSH?",
                "opcoes": ["22", "80", "110", "53"],
                "resposta_correta": "22",
            },
            {
                "pergunta": "Qual protocolo garante entrega ordenada e sem perdas?",
                "opcoes": ["TCP", "UDP", "ICMP", "IP"],
                "resposta_correta": "TCP",
            },
            {
                "pergunta": "Qual protocolo é usado para sincronização de relógios?",
                "opcoes": ["NTP", "FTP", "DNS", "HTTP"],
                "resposta_correta": "NTP",
            },
            {
                "pergunta": "Qual subrede corresponde a 255.255.255.0?",
                "opcoes": ["/24", "/16", "/8", "/32"],
                "resposta_correta": "/24",
            },
            {
                "pergunta": "Qual comando verifica conectividade em nível de rede?",
                "opcoes": ["ping", "ls", "copy", "telnet"],
                "resposta_correta": "ping",
            },
            {
                "pergunta": "Qual protocolo é usado para navegação web segura?",
                "opcoes": ["HTTPS", "SMTP", "POP3", "Telnet"],
                "resposta_correta": "HTTPS",
            },
            {
                "pergunta": "Qual dispositivo conecta redes diferentes e toma decisões de roteamento?",
                "opcoes": ["Roteador", "Hub", "Switch", "Repeater"],
                "resposta_correta": "Roteador",
            },
            {
                "pergunta": "Qual protocolo coleta informações de dispositivos em rede?",
                "opcoes": ["SNMP", "ARP", "DNS", "DHCP"],
                "resposta_correta": "SNMP",
            },
            {
                "pergunta": "Qual camada do modelo OSI trata da transmissão de bits na mídia?",
                "opcoes": ["Física", "Rede", "Aplicação", "Transporte"],
                "resposta_correta": "Física",
            },
            {
                "pergunta": "Qual protocolo permite acesso remoto seguro em terminal?",
                "opcoes": ["SSH", "FTP", "SMTP", "HTTP"],
                "resposta_correta": "SSH",
            },
            {
                "pergunta": "Qual é o número de bits de um endereço IPv4?",
                "opcoes": ["32", "16", "64", "128"],
                "resposta_correta": "32",
            },
            {
                "pergunta": "Qual endereço é reservado para loopback?",
                "opcoes": ["127.0.0.1", "192.168.0.1", "10.0.0.1", "172.16.0.1"],
                "resposta_correta": "127.0.0.1",
            },
            {
                "pergunta": "Qual protocolo usa porta 53?",
                "opcoes": ["DNS", "HTTP", "SMTP", "IMAP"],
                "resposta_correta": "DNS",
            },
            {
                "pergunta": "Qual categoria de endereço IP é usada para multicast?",
                "opcoes": ["Classe D", "Classe A", "Classe B", "Classe C"],
                "resposta_correta": "Classe D",
            },
            {
                "pergunta": "Qual protocolo realiza mapeamento de endereço MAC para IP?",
                "opcoes": ["ARP", "ICMP", "TCP", "UDP"],
                "resposta_correta": "ARP",
            },
            {
                "pergunta": "Qual ferramenta verifica portas abertas em um host?",
                "opcoes": ["nmap", "ping", "traceroute", "arp"],
                "resposta_correta": "nmap",
            },
            {
                "pergunta": "Qual camada do modelo OSI garante entrega confiável de dados?",
                "opcoes": ["Transporte", "Enlace", "Sessão", "Rede"],
                "resposta_correta": "Transporte",
            },
            {
                "pergunta": "Qual protocolo é usado para obter IP automaticamente em redes locais?",
                "opcoes": ["DHCP", "FTP", "SMTP", "IMAP"],
                "resposta_correta": "DHCP",
            },
        ]

    def obter_perguntas(self):
        """Retorna uma cópia da lista de perguntas (evita mutação externa)."""
        return list(self._perguntas)

    def embaralhar(self):
        """Retorna as perguntas em ordem aleatória (não altera a ordem interna)."""
        perguntas = self.obter_perguntas()
        random.shuffle(perguntas)
        return perguntas

    def selecionar_aleatoria(self):
        """Sorteia uma única pergunta ao acaso."""
        return random.choice(self.obter_perguntas())


# Alias em inglês (compatibilidade). Código novo deve usar BancoPerguntas.
BancoPerguntasRedes = BancoPerguntas
