using System.Collections.Generic;
using System.Windows;
using Microsoft.Win32;
using TradosKiller.Core.Models;
using TradosKiller.Core.Services;
using System.ComponentModel;
using System.Windows.Data;
using System.Windows.Controls;
using System.Windows.Input; // Necessário para as Hotkeys

namespace TradosKiller.Core.Views
{
    public partial class MainWindow : Window
    {
        private string? _openedFilePath;
        private SdlParser _parser = new SdlParser();
        private List<TranslationSegment> _segments = new();

        public MainWindow() => InitializeComponent();

        // --- O "CTRL + ENTER" MATADOR (Sem Preview, Sem Lag) ---
        private void dgSegments_PreviewKeyDown(object sender, KeyEventArgs e)
        {
            // Detecta Ctrl + Enter
            if (e.Key == Key.Enter && (Keyboard.Modifiers & ModifierKeys.Control) == ModifierKeys.Control)
            {
                var selectedSegment = dgSegments.SelectedItem as TranslationSegment;
                if (selectedSegment != null)
                {
                    // 1. Marca como confirmado (isso vai disparar o verde no XML que fizemos)
                    selectedSegment.IsConfirmed = true;

                    // 2. Força a atualização visual da linha
                    dgSegments.Items.Refresh();

                    // 3. Pula para a próxima linha automaticamente
                    if (dgSegments.SelectedIndex < dgSegments.Items.Count - 1)
                    {
                        dgSegments.SelectedIndex++;
                        dgSegments.ScrollIntoView(dgSegments.SelectedItem);
                    }

                    // Impede que o 'Enter' padrão do Windows crie uma nova linha na célula
                    e.Handled = true;
                }
            }
        }

        // --- MOTOR DE BUSCA (Rápido como um tiro) ---
        private void txtFilter_TextChanged(object sender, TextChangedEventArgs e)
        {
            if (dgSegments.ItemsSource == null) return;

            ICollectionView view = CollectionViewSource.GetDefaultView(dgSegments.ItemsSource);
            
            if (string.IsNullOrWhiteSpace(txtFilter.Text))
            {
                view.Filter = null;
            }
            else
            {
                string query = txtFilter.Text.ToLower();
                view.Filter = obj =>
                {
                    var seg = obj as TranslationSegment;
                    if (seg == null) return false;
                    return (seg.Source?.ToLower().Contains(query) ?? false) ||
                           (seg.Target?.ToLower().Contains(query) ?? false) ||
                           (seg.Id?.ToLower().Contains(query) ?? false);
                };
            }
        }

        private void btnOpen_Click(object sender, RoutedEventArgs e)
        {
            var openFileDialog = new OpenFileDialog { Filter = "SDLXLIFF files (*.sdlxliff)|*.sdlxliff" };
            if (openFileDialog.ShowDialog() == true)
            {
                _openedFilePath = openFileDialog.FileName;
                _segments = _parser.ExtractSegments(_openedFilePath);
                dgSegments.ItemsSource = _segments; 
            }
        }

        private void btnSave_Click(object sender, RoutedEventArgs e)
        {
            var saveFileDialog = new SaveFileDialog { Filter = "SDLXLIFF files (*.sdlxliff)|*.sdlxliff" };
            if (saveFileDialog.ShowDialog() == true && !string.IsNullOrEmpty(_openedFilePath))
            {
                _parser.SaveFile(_openedFilePath, saveFileDialog.FileName, _segments);
                MessageBox.Show("Trabalho salvo! O arquivo está pronto para entrega (Confirmado).");
            }
        }
    }
}