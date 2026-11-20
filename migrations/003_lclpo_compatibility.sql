-- Compatibilidade de fontes com o lclpo. SICRO permanece como código físico
-- para não quebrar releases existentes; a API expõe esse código como SICRO3.
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'DER';
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'SICRO3';
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'ORSE';
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'SBC';
ALTER TYPE source_kind ADD VALUE IF NOT EXISTS 'OUTRAS';

INSERT INTO sources(code, name, publisher) VALUES
  ('DER', 'Departamentos Estaduais de Rodagem', 'Órgãos estaduais'),
  ('SICRO3', 'Sistema de Custos Referenciais de Obras', 'DNIT'),
  ('ORSE', 'Orçamento de Obras de Sergipe', 'CEHOP/SE'),
  ('SBC', 'Sistema Boletim de Custos', 'SBC'),
  ('OUTRAS', 'Outras fontes de referência', 'Usuário')
ON CONFLICT (code) DO NOTHING;
