import pandas as pd
import re
import phonenumbers

def padronizar_telefone(numero):
    """
    Usa a biblioteca phonenumbers para analisar, validar e formatar um número de telefone.
    Retorna uma string de dígitos no formato DDI+DDD+Numero.
    """
    if not numero or pd.isna(numero):
        return ""
    
    try:
        # O 'BR' ajuda a biblioteca a entender números sem código de país (ex: (51) 99141-3631)
        num_parseado = phonenumbers.parse(str(numero), "BR")
        
        # Verifica se é um número possível e válido
        if phonenumbers.is_valid_number(num_parseado):
            # Formata para o padrão internacional E.164 (ex: +5551991413631)
            # e depois remove o '+' para manter a consistência com o banco.
            return phonenumbers.format_number(num_parseado, phonenumbers.PhoneNumberFormat.E164).replace('+', '')
        else:
            # Se a biblioteca não considerar o número válido, retorna apenas os dígitos (comportamento antigo)
            return re.sub(r'\D', '', str(numero))
    except phonenumbers.phonenumberutil.NumberParseException:
        # Se a biblioteca não conseguir nem "ler" o número, retorna apenas os dígitos
        return re.sub(r'\D', '', str(numero))

def formatar_data(coluna_data):
    """
    Converte uma coluna de data para o formato dd/mm/YYYY,
    forçando a interpretação do dia primeiro.
    """
    datas_convertidas = pd.to_datetime(coluna_data, errors='coerce', dayfirst=True)
    return datas_convertidas.dt.strftime('%d/%m/%Y')