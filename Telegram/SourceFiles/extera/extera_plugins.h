/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#pragma once

#include <QtCore/QJsonObject>
#include <QtCore/QJsonValue>

namespace Api {
struct MessageToSend;
} // namespace Api

namespace Extera {

void StartPlugins();
[[nodiscard]] bool PluginsRunning();
[[nodiscard]] QString PluginsError();
[[nodiscard]] QString PluginsLog();
[[nodiscard]] QString PluginsFolder();

[[nodiscard]] bool PluginsOption(const QString &key);
void SetPluginsOption(const QString &key, bool value);

[[nodiscard]] bool RussianInterface();
[[nodiscard]] QString Phrase(const QString &en, const QString &ru);

QJsonValue PluginsRequest(
	const QString &name,
	const QJsonObject &payload = QJsonObject(),
	QString *error = nullptr);

[[nodiscard]] bool ProcessOutgoing(Api::MessageToSend &message);

} // namespace Extera
