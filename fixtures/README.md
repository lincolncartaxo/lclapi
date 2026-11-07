# Fixtures de integração

Os pacotes brutos SINAPI (`.zip`) e SICRO (`.7z`) usados na validação local não são versionados neste repositório por tamanho e por serem arquivos de distribuição externa. Para executar os testes de integração completos, coloque os arquivos fornecidos pelo usuário nesta pasta com os nomes esperados pelo teste:

- `SINAPI-2026-08-formato-xlsx.zip`
- `pb-07-2026.7z`

Sem esses arquivos, os testes ficam marcados como `skipped`; os parsers continuam disponíveis para importação via CLI e API.
