insert into regions(code, name, region_type) values
 ('AC', 'Acre', 'UF'), ('AL', 'Alagoas', 'UF'), ('AP', 'Amapá', 'UF'), ('AM', 'Amazonas', 'UF'),
 ('BA', 'Bahia', 'UF'), ('CE', 'Ceará', 'UF'), ('DF', 'Distrito Federal', 'UF'), ('ES', 'Espírito Santo', 'UF'),
 ('GO', 'Goiás', 'UF'), ('MA', 'Maranhão', 'UF'), ('MT', 'Mato Grosso', 'UF'), ('MS', 'Mato Grosso do Sul', 'UF'),
 ('MG', 'Minas Gerais', 'UF'), ('PA', 'Pará', 'UF'), ('PB', 'Paraíba', 'UF'), ('PR', 'Paraná', 'UF'),
 ('PE', 'Pernambuco', 'UF'), ('PI', 'Piauí', 'UF'), ('RJ', 'Rio de Janeiro', 'UF'), ('RN', 'Rio Grande do Norte', 'UF'),
 ('RS', 'Rio Grande do Sul', 'UF'), ('RO', 'Rondônia', 'UF'), ('RR', 'Roraima', 'UF'), ('SC', 'Santa Catarina', 'UF'),
 ('SP', 'São Paulo', 'UF'), ('SE', 'Sergipe', 'UF'), ('TO', 'Tocantins', 'UF')
on conflict (code) do update set name=excluded.name, region_type=excluded.region_type;
