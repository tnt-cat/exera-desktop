/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#pragma once

class DocumentData;
class HistoryItem;

namespace Ui {
class GenericBox;
class Show;
} // namespace Ui

namespace Window {
class SessionController;
} // namespace Window

namespace Extera {

void PluginsBox(not_null<Ui::GenericBox*> box);

void ShowInstallPlugin(
	std::shared_ptr<Ui::Show> show,
	const QString &path,
	Fn<void()> done = nullptr);

[[nodiscard]] bool OpenPluginDocument(
	not_null<Window::SessionController*> controller,
	not_null<DocumentData*> document,
	HistoryItem *item);

} // namespace Extera
