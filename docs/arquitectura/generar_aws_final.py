#!/usr/bin/env python3
"""Genera docs/arquitectura/aws-final.drawio: la arquitectura AWS desplegada y probada de Nodo Ruta.

Solo biblioteca estandar. Uso: python docs/arquitectura/generar_aws_final.py
Fuente de verdad: infra/aws/01-red.yaml, 02-datos.yaml, 03-computo.yaml, 04-front.yaml,
infra/aws/iam/politica-github-actions.json y .github/workflows/aws.yml.
Si se edita a mano en draw.io, edita el .drawio y no regeneres (se pierde el cambio).
"""
from pathlib import Path
from xml.sax.saxutils import quoteattr

cells = []
_id = [1]


def nid(p):
    _id[0] += 1
    return f"{p}{_id[0]}"


def add(value, style, x, y, w, h, cid=None):
    cid = cid or nid("c")
    cells.append(f'<mxCell id="{cid}" value={quoteattr(value)} style={quoteattr(style)} vertex="1" parent="1">'
                 f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    return cid


def edge(src, tgt, label="", dashed=False, exit=None, entry=None, color="#545B64", pts=None, both=False):
    cid = nid("e")
    st = ("edgeStyle=orthogonalEdgeStyle;rounded=1;jettySize=auto;html=1;endArrow=block;endFill=1;"
          f"strokeColor={color};strokeWidth=1.5;fontSize=10;fontColor=#232F3E;labelBackgroundColor=#FFFFFF;")
    if dashed:
        st += "dashed=1;dashPattern=6 4;"
    if both:
        st += "startArrow=block;startFill=1;"
    if exit:
        st += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
    if entry:
        st += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
    geo = '<mxGeometry relative="1" as="geometry">'
    if pts:
        geo += '<Array as="points">' + "".join(f'<mxPoint x="{a}" y="{b}"/>' for a, b in pts) + "</Array>"
    geo += "</mxGeometry>"
    cells.append(f'<mxCell id="{cid}" value={quoteattr(label)} style={quoteattr(st)} edge="1" parent="1" '
                 f'source="{src}" target="{tgt}">{geo}</mxCell>')
    return cid


LBL = "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontColor=#232F3E;"
COL = {"net": "#8C4FFF", "comp": "#ED7100", "sto": "#7AA116", "db": "#C925D1", "mgmt": "#E7157B", "sec": "#DD344C",
       "dev": "#C925D1", "gen": "#232F3E"}


def icon(name, col, value, x, y, s=56, right=False, left=False):
    st = (f"sketch=0;outlineConnect=0;gradientColor=none;fillColor={COL[col]};strokeColor=#ffffff;dashed=0;aspect=fixed;"
          f"{LBL}shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{name};")
    if right:
        st += "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=4;"
    if left:
        st += "labelPosition=left;verticalLabelPosition=middle;align=right;verticalAlign=middle;spacingRight=4;"
    return add(value, st, x, y, s, s)


def shape(name, col, value, x, y, s=56, right=False):
    st = (f"sketch=0;outlineConnect=0;gradientColor=none;fillColor={COL[col]};strokeColor=none;dashed=0;aspect=fixed;"
          f"pointerEvents=1;{LBL}shape=mxgraph.aws4.{name};")
    if right:
        st += "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=4;"
    return add(value, st, x, y, s, s)


def group(icon_name, label, x, y, w, h, stroke, font, fill="none", dashed=0):
    st = ("points=[];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=1;container=0;"
          f"pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.{icon_name};"
          f"strokeColor={stroke};fillColor={fill};verticalAlign=top;align=left;spacingLeft=30;fontColor={font};dashed={dashed};")
    return add(label, st, x, y, w, h)


def box(label, x, y, w, h, stroke="#147EBA", font="#147EBA", dashed=1, fill="none", size=12, align="center"):
    st = (f"align={align};spacingLeft=10;spacingRight=10;fillColor={fill};strokeColor={stroke};dashed={dashed};verticalAlign=top;fontStyle=1;fontColor={font};"
          f"whiteSpace=wrap;html=1;fontSize={size};")
    return add(label, st, x, y, w, h)


def text(value, x, y, w, h, size=11, extra="", align="left"):
    st = f"text;html=1;whiteSpace=wrap;align={align};verticalAlign=top;fontSize={size};fontColor=#232F3E;{extra}"
    return add(value, st, x, y, w, h)


# ---------------- lienzo ----------------
text("<b>Nodo Ruta · Arquitectura AWS final (desplegada y probada)</b>", 20, 6, 900, 24, 16)

# columna izquierda: usuario
usuario = shape("user", "gen", "Operaciones<br>(solo la IP de CidrAcceso)", 40, 330, 52)

# AWS Cloud + Region
group("group_aws_cloud_alt", "AWS Cloud", 190, 40, 1330, 1010, "#232F3E", "#232F3E")
group("group_region", "Región us-east-2 (Ohio)", 210, 80, 1290, 700, "#147EBA", "#147EBA", dashed=1)

# front: CloudFront y S3 del front
cf = icon("cloudfront", "net", "CloudFront<br>HTTPS *.cloudfront.net<br>(Function: solo CidrAcceso)", 240, 340, 64)
s3f = icon("s3", "sto", "S3 del front<br>privado (OAC)", 240, 120, 56, right=True)

# VPC
group("group_vpc2", "VPC 10.20.0.0/16 (nodo-ruta-red)", 420, 110, 700, 650, "#8C4FFF", "#8C4FFF")
igw = shape("internet_gateway", "net", "Internet<br>Gateway", 440, 340, 48, right=True)
alb = icon("application_load_balancer", "net", "ALB (HTTP 80)<br>403 sin X-Origin-Verify", 735, 150, 56, right=True)

# AZ A
box("Zona de disponibilidad A", 560, 250, 260, 490, align="right")
group("group_security_group", "Subred pública A", 575, 285, 230, 215, "#7AA116", "#248814", fill="#F2F8EE")
ec2a = icon("ec2", "comp", "EC2 A<br>app :8080 + pedidos<br>IP pública, sin NAT", 590, 325, 56, right=True)
group("group_security_group", "Subred privada A", 575, 530, 230, 195, "#00A4A6", "#147EBA", fill="#E6F6F7")
rds = icon("rds", "db", "RDS PostgreSQL 17<br>db.t4g.micro<br>Single-AZ", 590, 575, 56)
# AZ B
box("Zona de disponibilidad B", 840, 250, 260, 490, align="left")
group("group_security_group", "Subred pública B", 855, 285, 230, 215, "#7AA116", "#248814", fill="#F2F8EE")
ec2b = icon("ec2", "comp", "EC2 B<br>app :8080 + pedidos<br>IP pública, sin NAT", 1010, 325, 56, left=True)
group("group_security_group", "Subred privada B", 855, 530, 230, 195, "#00A4A6", "#147EBA", fill="#E6F6F7")
text("Sin instancia: el <i>subnet group</i> de RDS abarca las dos zonas, pero la base corre solo en la zona A.",
     870, 640, 200, 60, 10, "fontStyle=2;")

# derecha: servicios fuera de la VPC
ssmp = icon("systems_manager", "mgmt", "SSM Parameter Store<br>SecureString: clave de la base<br>y clave de origen", 1260, 140, 56)
s3b = icon("s3", "sto", "S3 de respaldos<br>pg_dump + sha256, versiones<br>expiración a 7 días", 1260, 325, 56)
ssm = icon("systems_manager", "mgmt", "Systems Manager<br>Session Manager y Run Command<br>(sin SSH, sin puerto 22)", 1260, 460, 56)
iam = icon("identity_and_access_management", "sec", "IAM: rol de instancia<br>(SSM, lectura de sus parámetros,<br>escritura en S3 de respaldos)", 1260, 620, 56)
box("Servicios regionales (fuera de la VPC)", 1200, 100, 280, 650, stroke="#879196", font="#232F3E", size=11)

# CI/CD (dentro de la cuenta, bajo la región)
gh = add("GitHub Actions<br>(solo rama main)", "rounded=1;whiteSpace=wrap;html=1;fillColor=#24292F;strokeColor=#24292F;"
         "fontColor=#FFFFFF;fontSize=11;fontStyle=1;", 30, 840, 120, 60)
nodo = add("scripts/aws_nodo.py<br>(alternativa local)", "rounded=1;whiteSpace=wrap;html=1;fillColor=#F2F3F3;"
           "strokeColor=#879196;fontColor=#232F3E;fontSize=11;", 30, 950, 120, 50)
rol = icon("identity_and_access_management", "sec", "Rol github-actions-nodo-ruta<br>(OIDC, sin claves)", 260, 830, 56)
cfn = icon("cloudformation", "mgmt", "CloudFormation<br>nodo-ruta-red, -datos, -computo, -front", 520, 830, 56)
text("Tamaño y clase de instancia según los parámetros de las plantillas. Todo con la etiqueta proyecto=nodo-ruta.",
     600, 800, 10, 10, 1, "fontColor=#FFFFFF;")  # marcador invisible para mantener la plantilla simple
cells.pop()

# leyenda
box("Leyenda", 760, 810, 740, 200, stroke="#879196", font="#232F3E", dashed=0, fill="#FAFAFA", size=12)
text("<b>Punto único de falla:</b> RDS Single-AZ (el plan gratuito no permite Multi-AZ). Se tolera la caída de una EC2, no la de la base.<br>"
     "<b>HTTPS solo hasta CloudFront:</b> CloudFront → ALB va en HTTP, protegido con el encabezado X-Origin-Verify.<br>"
     "<b>Grupos de seguridad:</b> SgAlb (80, solo CidrAcceso y CloudFront) → SgEc2 (8080, solo desde SgAlb) → SgRds (5432, solo desde SgEc2).<br>"
     "<b>Etiqueta:</b> proyecto=nodo-ruta en todos los recursos. <b>Costo:</b> consume créditos por hora; destruir al terminar "
     "(<i>python scripts/aws_nodo.py destruir</i>).<br>"
     "<b>Línea punteada:</b> acceso de administración, secretos y respaldos. <b>Línea continua:</b> tráfico de la solicitud o del despliegue.",
     775, 840, 710, 180, 11)

# ---------------- flechas ----------------
edge(usuario, cf, "HTTPS", exit=(1, 0.5), entry=(0, 0.5))
edge(cf, s3f, "“/” (interfaz estática)", entry=(0.5, 1), exit=(0.5, 0))
edge(cf, alb, "/pedidos y /health · HTTP 80<br>+ X-Origin-Verify, sin caché", exit=(1, 0.3), entry=(0, 0.5),
     pts=[(410, 358), (410, 178)])
edge(alb, ec2a, "SgAlb → SgEc2 :8080", exit=(0.25, 1), entry=(0.5, 0), pts=[(749, 235), (618, 235)])
edge(alb, ec2b, "", exit=(0.75, 1), entry=(0.5, 0), pts=[(777, 235), (1038, 235)])
edge(ec2a, rds, "SgEc2 → SgRds :5432", exit=(0.5, 1), entry=(0.5, 0))
edge(ec2b, rds, "", exit=(0.5, 1), entry=(1, 0.5), pts=[(1038, 603)])
edge(ec2b, ssmp, "lee secretos", dashed=True, exit=(1, 0.15), entry=(0, 0.5), pts=[(1150, 342), (1150, 168)])
edge(ec2b, s3b, "pg_dump", dashed=True, exit=(1, 0.5), entry=(0, 0.5))
edge(ssm, ec2b, "", dashed=True, exit=(0, 0.5), entry=(1, 0.85), pts=[(1130, 488), (1130, 373)])
edge(iam, ssm, "", dashed=True, exit=(0.5, 0), entry=(0.5, 1))
edge(gh, rol, "OIDC", exit=(1, 0.5), entry=(0, 0.5))
edge(rol, cfn, "asume el rol", exit=(1, 0.5), entry=(0, 0.5))
edge(nodo, cfn, "mismas plantillas", dashed=True, exit=(1, 0.5), entry=(0.5, 1), pts=[(548, 975)])
edge(cfn, igw, "crea y actualiza<br>las 4 pilas", exit=(0.5, 0), entry=(0.5, 1), pts=[(548, 800), (464, 800)])

xml = ('<mxfile host="estudIA" type="device"><diagram id="aws-final" name="AWS final">'
       '<mxGraphModel dx="1600" dy="1100" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
       'page="1" pageScale="1" pageWidth="1600" pageHeight="1100" math="0" shadow="0">'
       '<root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(cells) + "</root></mxGraphModel></diagram></mxfile>")
destino = Path(__file__).resolve().parent / "aws-final.drawio"
destino.write_text(xml, encoding="utf-8", newline="\n")
print(f"escrito {destino}")
