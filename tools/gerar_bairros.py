# -*- coding: utf-8 -*-
"""Gera lider/bairros.json a partir da tabela de entregas (Entregas_com_distancias.txt). Rodar só se a tabela mudar."""
import json, re
REGIOES = {1: ("Vila Isa (Sul)", "20 a 30 min"), 2: ("Centro e Ilha dos Araújos", "40 a 50 min"), 3: ("Vila Bretas e São Paulo", "35 a 45 min"),
           4: ("Santa Rita e JK", "35 a 45 min"), 5: ("Jardim Pérola, Altinópolis e Planalto", "35 a 45 min"), 6: ("Santos Dumont, Santa Helena e SIR", "50 a 60 min")}
DADOS = """
1|Asteca|0,6 km|2 min|Vizinho imediato (via R. Arapoca / R. Treze)
1|Jardim Ipê|1,0 km|2 min|Bairro da loja
1|Jardim Vera Cruz|1,2 km|4 min|Acesso direto (via R. Martim Afonso)
1|Vale do Sol (I, II e III)|1,2 km|3 min|Colado no Jardim Ipê (via Av. A)
1|São Raimundo|1,7 km|5 min|Acesso direto (via R. Américo Vespúcio)
1|Conquista|2,3 km|5 min|Sentido Av. da Lagoa
1|Jardim Primavera|2,3 km|7 min|Próximo à BR-116
1|Vila Isa|2,7 km|6 min|Eixo principal da região (via BR-116)
1|Vila dos Montes|3,0 km|7 min|Região do Cidade Jardim (via R. Ipanema)
1|Cidade Jardim|3,1 km|7 min|Região sul (via R. Ipanema)
1|Elvamar|3,7 km|8 min|Próximo à cabeceira da ponte (BR-116)
1|Vila Parque São João|6,3 km|8 min|Saída Sul pela BR-116
2|São Tarcísio|9,6 km|23 min|Beira-rio / acesso pela BR-116
2|Centro|9,1 km|22 min|Via BR-116 / Rua Israel Pinheiro
2|Esplanada|9,6 km|21 min|Acesso via Israel Pinheiro
2|Ilha dos Araújos|9,8 km|23 min|Travessia da ponte da Ilha
2|São Pedro|10,3 km|23 min|Região da Univale / Av. Minas Gerais
2|Belvedere|10,8 km|24 min|Parte alta / Av. Minas Gerais
2|Universitário|11,2 km|24 min|Região do Campus II Univale
3|São Paulo|5,1 km|13 min|Logo após a ponte (via BR-116)
3|Vila Rica|5,3 km|12 min|Próximo à BR-116 / Vila Bretas
3|Vila Bretas|5,4 km|12 min|Acesso rápido pela BR-116
3|Santa Terezinha|6,0 km|16 min|Entre Vila Bretas e Centro
3|Lourdes|6,6 km|14 min|Sentido Av. Brasil / BR-116
3|São Geraldo|8,0 km|16 min|Próximo ao Lourdes / Grã-Duquesa
3|Vila Mariana|10,0 km|19 min|Sentido Grã-Duquesa / Centro
3|Grã-Duquesa|10,1 km|19 min|Acesso via BR-116 / Av. Brasil
3|Santo Agostinho|10,1 km|20 min|Região do Grã-Duquesa
4|Nossa Senhora de Fátima|6,2 km|15 min|Início do corredor da Av. JK
4|Jardim Alice|6,4 km|14 min|Próximo ao trevo da JK
4|Park da Fraternidade|6,4 km|15 min|Região do Jardim Pérola / JK
4|JK (I, II e III)|6,5 km|14 min|Corredor principal da Av. JK
4|Sagrada Família|6,6 km|15 min|Próximo à Av. JK / Vila Império
4|Vila Ricardão|6,9 km|16 min|Adjacente ao Santa Rita / JK
4|Vila Império|7,0 km|16 min|Próximo ao Santa Rita
4|Castanheiras|7,3 km|16 min|Região do Santa Rita / JK
4|Santa Rita|7,5 km|17 min|Centro comercial da região
4|Kennedy|8,1 km|18 min|Após o Santa Rita (sentido Penha)
4|Penha|8,8 km|20 min|Sentido saída para Ipatinga
4|Caravelas|9,1 km|20 min|Próximo à Penha / BR-381
4|Vitória|10,2 km|22 min|Final da Av. JK / saída Ipatinga
4|Distrito Industrial|10,5 km|22 min|Saída para Ipatinga (BR-381)
5|Jardim Pérola|5,8 km|14 min|Acesso direto pela BR-116
5|Vila Ozanan|7,4 km|16 min|Próximo ao Jardim Pérola / Altinópolis
5|Altinópolis|7,9 km|17 min|Acesso pela BR-116
5|Planalto|8,9 km|17 min|Continuação da BR-116 (Norte)
5|Jardim do Trevo|11,0 km|26 min|Trevo norte / saída Teófilo Otoni
5|Morada do Vale (I, II e III)|11,2 km|19 min|Parte alta norte (via BR-116)
5|Esperança|12,4 km|21 min|Região norte (via BR-116)
6|Nossa Senhora das Graças|11,4 km|23 min|Acesso via Av. Minas Gerais / BR-116
6|Santa Helena|11,8 km|23 min|Região do Santos Dumont
6|Santos Dumont I|12,5 km|26 min|Acesso via Israel Pinheiro / Av. Minas Gerais
6|Cardo|18,4 km|26 min|Acesso mais rápido via Anel Rodoviário (BR-381)
6|Conjunto SIR|18,7 km|26 min|Acesso mais rápido via Anel Rodoviário (BR-381)
6|Santos Dumont II|19,8 km|29 min|Acesso mais rápido via Anel Rodoviário (BR-381)
6|Capim|20,3 km|29 min|Extremo leste (via Anel Rodoviário)
6|Chácaras Canaã|23,6 km|29 min|Saída para Mantena (BR-259)
"""
ALIAS = {"Asteca": ["Azteca", "Aztecas"], "Jardim Vera Cruz": ["Vera Cruz"], "Vale do Sol (I, II e III)": ["Vale do Sol", "Vale do Sol I", "Vale do Sol II", "Vale do Sol III"],
         "JK (I, II e III)": ["JK", "JK I", "JK II", "JK III", "Nova JK"], "Morada do Vale (I, II e III)": ["Morada do Vale", "Morada do Vale I", "Morada do Vale II", "Morada do Vale III"],
         "Park da Fraternidade": ["Fraternidade", "Park Fraternidade"], "Santos Dumont I": ["Santos Dumont"], "Santos Dumont II": ["Santos Dumont 2"],
         "Chácaras Canaã": ["Canaã", "Chacaras Canaa"], "Grã-Duquesa": ["Gra Duquesa", "Grã Duquesa"], "Conjunto SIR": ["SIR"]}
out = []
for lin in DADOS.strip().splitlines():
    r, b, d, t, o = lin.split("|")
    r = int(r)
    out.append({"bairro": b, "zona": r, "regiao": REGIOES[r][0], "prazo": REGIOES[r][1], "dist": d, "tempo": t, "obs": o, "alias": ALIAS.get(b, [])})
json.dump({"saida": "Rua Arapoca, 26 (Jardim Ipê)", "regioes": {str(k): {"nome": v[0], "prazo": v[1]} for k, v in REGIOES.items()}, "bairros": out},
          open("lider/bairros.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out), "bairros")
