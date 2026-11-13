/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#pragma once

namespace Extera::Python {

using HostCallback = Fn<QByteArray(
	const QByteArray &name,
	const QByteArray &payload)>;

bool Start(
	const QString &runtimeDir,
	const QString &sdkDir,
	HostCallback host);
[[nodiscard]] bool Running();
[[nodiscard]] QString Error();

[[nodiscard]] QByteArray Call(
	const QByteArray &name,
	const QByteArray &payload);

} // namespace Extera::Python
