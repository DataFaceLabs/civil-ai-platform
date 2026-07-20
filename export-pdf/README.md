# M1-X2 LibreOffice DOCX→PDF converter (container Lambda).
#
# Build + deploy: scripts/deploy-export-pdf.sh
# Local smoke (requires Docker):
#   docker build -t civilai-export-pdf export-pdf
#   docker run --rm -v /tmp:/work -e CIVILAI_APP_BUCKET=... \
#     --entrypoint soffice civilai-export-pdf \
#     --headless --convert-to pdf --outdir /work /work/study.docx
#
# Fonts: Libre Franklin + Source Sans 3 (OFL) under fonts/.
