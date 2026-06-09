#!/usr/bin/env bash
#
# Сборка .deb-пакета MetadataViewer.
#
# Пакет устанавливает Python-модуль в dist-packages, лаунчер /usr/bin/metadataviewer
# и ярлык приложения. Зависит от системного python3 + tkinter; библиотеки для
# расширенных метаданных (Pillow, mutagen, pypdf) идут в Recommends.
#
# Использование:  packaging/build_deb.sh [версия]
# Результат:      dist/metadataviewer_<версия>_all.deb
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-$(python3 -c 'import metadataviewer; print(metadataviewer.__version__)' 2>/dev/null || echo 1.1.0)}"
PKG="metadataviewer"
ARCH="all"

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

DEST="$BUILD/${PKG}_${VERSION}_${ARCH}"
PYDIR="$DEST/usr/lib/python3/dist-packages/metadataviewer"

echo ">> Подготовка дерева пакета в $DEST"
mkdir -p "$DEST/DEBIAN" \
         "$PYDIR" \
         "$DEST/usr/bin" \
         "$DEST/usr/share/applications" \
         "$DEST/usr/share/doc/$PKG"

# Python-модуль
cp "$ROOT"/metadataviewer/*.py "$PYDIR/"

# Лаунчер
install -m 0755 "$ROOT/packaging/metadataviewer.launcher" "$DEST/usr/bin/metadataviewer"

# Ярлык приложения
install -m 0644 "$ROOT/packaging/metadataviewer.desktop" \
        "$DEST/usr/share/applications/metadataviewer.desktop"

# Документация и copyright
install -m 0644 "$ROOT/LICENSE" "$DEST/usr/share/doc/$PKG/copyright"
gzip -9 -c "$ROOT/README.md" > "$DEST/usr/share/doc/$PKG/README.md.gz"

# control
INSTALLED_KB=$(du -ks "$DEST/usr" | cut -f1)
cat > "$DEST/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8), python3-tk
Recommends: python3-pil, python3-pil.imagetk, python3-mutagen, python3-pypdf
Installed-Size: $INSTALLED_KB
Maintainer: MetadataViewer
Homepage: https://github.com/SyberianIT/MetadataViever-
Description: Просмотр метаданных файлов (GUI и CLI)
 MetadataViewer показывает метаданные изображений (EXIF/GPS), аудио, видео,
 PDF, документов Office и архивов, считает контрольные суммы и умеет удалять
 метаданные из изображений. Включает графический интерфейс на Tkinter и
 режим командной строки.
EOF

echo ">> Сборка .deb"
mkdir -p "$ROOT/dist"
OUTPUT="$ROOT/dist/${PKG}_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$DEST" "$OUTPUT"

echo ">> Готово: $OUTPUT"
dpkg-deb --info "$OUTPUT"
echo "---- содержимое ----"
dpkg-deb --contents "$OUTPUT"
