import torch
from torch import nn
from torch.nn import functional as F


class LightCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 16, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
            nn.Conv2d(128, 256, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d((1, 1)),
        )

    def forward(self, x):
        x = self.features(x)
        return torch.flatten(x, 1)


class TemporalAttention(nn.Module):
    def __init__(self, hidden_size=64):
        super().__init__()
        self.attn = nn.Linear(hidden_size, 1)

    def forward(self, gru_out):
        scores = self.attn(gru_out)
        weights = F.softmax(scores, dim=1)
        return (gru_out * weights).sum(dim=1), weights


class PhoneCNNGRU(nn.Module):
    def __init__(self, num_classes=2):
        super().__init__()
        self.cnn = LightCNN()
        self.gru = nn.GRU(
            input_size=256,
            hidden_size=64,
            num_layers=2,
            batch_first=True,
            dropout=0.3,
        )
        self.attention = TemporalAttention(hidden_size=64)
        self.classifier = nn.Sequential(
            nn.BatchNorm1d(64),
            nn.Linear(64, 32),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(32, num_classes),
        )

    def forward(self, x):
        batch_size, time_steps, channels, height, width = x.shape
        x = x.view(batch_size * time_steps, channels, height, width)
        features = self.cnn(x)
        features = features.view(batch_size, time_steps, -1)
        gru_out, _ = self.gru(features)
        context, _ = self.attention(gru_out)
        return self.classifier(context)
